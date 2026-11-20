"""BE-083 — EXPLAIN das consultas críticas com volume (mapa, chats, não lidas, nota
média, notificações, vitrine e quadros).

O banco recebe um volume realista por SQL (`generate_series`, gatilhos desligados só
durante a carga e religados antes da medição; tudo some no rollback do teste):
2.000 oficinas públicas com ponto no mapa, 2.000 clientes, 12.000 atendimentos e
orçamentos aprovados, 12.000 avaliações, 40.000 mensagens e 60.000 notificações.
Depois do `ANALYZE`, cada rota crítica é chamada de verdade, as consultas que ela
fez são capturadas e o plano de cada `SELECT` não pode ter varredura sequencial em
tabela grande (≥ `BIG_TABLE_ROWS` linhas estimadas).

`SAM_PERF_REPORT=<arquivo>` grava as medições (tempo de execução do EXPLAIN ANALYZE)
usadas no ADR 0023.
"""

import json
import os

import pytest
from conftest import open_account_session
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.slow]

BIG_TABLE_ROWS = 10_000
N = 2000  # oficinas e clientes

TRIGGERS_OFF = [
    "attendance",
    "budget",
    "budget_item",
    "review",
    "promotion",
    "promotion_advertisement",
]

SEED = f"""
SELECT setseed(0.42);  -- coordenadas aleatórias, mas iguais em toda execução

INSERT INTO point_of_interest (name, type, latitude, longitude, address)
SELECT 'Oficina ' || g, 'oficina', -5.09 + (random() - 0.5) * 4, -42.80 + (random() - 0.5) * 4, 'Rua ' || g
FROM generate_series(1, {N}) g;

INSERT INTO workshop (name_fantasy, name_responsible, email, password_hash, cnpj, id_point_of_interest)
SELECT 'Oficina ' || p.id_point_of_interest, 'Responsável', 'carga' || p.id_point_of_interest || '@oficina.test',
       'x', lpad(p.id_point_of_interest::text, 14, '0'), p.id_point_of_interest
FROM point_of_interest p WHERE p.name LIKE 'Oficina %' AND p.address LIKE 'Rua %';

INSERT INTO pag_workshop (id_workshop, description)
SELECT id_workshop, 'Página' FROM workshop WHERE email LIKE 'carga%';

INSERT INTO workshop_service (id_workshop, id_service, price_base, duration_estimate)
SELECT w.id_workshop, s.id_service, 100, 60
FROM workshop w CROSS JOIN LATERAL (
    SELECT id_service FROM service ORDER BY id_service OFFSET (w.id_workshop % 50) LIMIT 2
) s WHERE w.email LIKE 'carga%';

INSERT INTO operation_hour (id_workshop, day_of_week, opening_time, closing_time)
SELECT w.id_workshop, d, '08:00', '18:00'
FROM workshop w CROSS JOIN generate_series(1, 6) d WHERE w.email LIKE 'carga%';

INSERT INTO client (name, email, password_hash)
SELECT 'Cliente ' || g, 'carga' || g || '@cliente.test', 'x' FROM generate_series(1, {N}) g;

INSERT INTO vehicle (id_client, brand, model, year_fabrication, year_model, plate, fuel, exchange, mileage_km)
SELECT c.id_client, 'Fiat', 'Uno', 2015, 2016,
       'ABC' || (c.id_client % 10) || chr((65 + (c.id_client / 10) % 26)::int) || lpad(((c.id_client / 260) % 100)::text, 2, '0'),
       'flex', 'manual', 50000
FROM client c WHERE c.email LIKE 'carga%';

WITH pairs AS (
    SELECT c.id_client, v.id_vehicle, w.id_workshop, k
    FROM client c
    JOIN vehicle v ON v.id_client = c.id_client
    JOIN LATERAL (SELECT id_workshop FROM workshop WHERE email LIKE 'carga%'
                  ORDER BY id_workshop OFFSET (c.id_client % {N}) LIMIT 1) w ON TRUE
    CROSS JOIN generate_series(1, 6) k
    WHERE c.email LIKE 'carga%'
)
INSERT INTO attendance (id_client, id_vehicle, id_workshop, status_attendance, date_attendance)
SELECT id_client, id_vehicle, id_workshop, 'delivered', NOW() - (k || ' days')::interval FROM pairs;

INSERT INTO budget (id_attendance, id_workshop, status_budget, total_price, date_response,
                    date_creation, date_validity)
SELECT id_attendance, id_workshop, 'approved', 150, NOW(), NOW() - interval '30 days', NOW() + interval '1 day'
FROM attendance WHERE id_client IN (SELECT id_client FROM client WHERE email LIKE 'carga%');

INSERT INTO review (id_budget, rating, comment)
SELECT id_budget, 1 + (id_budget % 5), 'Bom' FROM budget
WHERE id_workshop IN (SELECT id_workshop FROM workshop WHERE email LIKE 'carga%');

INSERT INTO chat (id_client, id_workshop)
SELECT DISTINCT a.id_client, a.id_workshop FROM attendance a
WHERE a.id_client IN (SELECT id_client FROM client WHERE email LIKE 'carga%');

INSERT INTO message (id_chat, id_client, id_workshop, content, date_sent)
SELECT ch.id_chat,
       CASE WHEN k % 2 = 0 THEN ch.id_client END,
       CASE WHEN k % 2 = 1 THEN ch.id_workshop END,
       'Mensagem ' || k, NOW() - (k || ' minutes')::interval
FROM chat ch CROSS JOIN generate_series(1, 20) k;

INSERT INTO notification (id_client, title, message, read_status)
SELECT c.id_client, 'Aviso', 'Mensagem ' || k, k % 3 = 0
FROM client c CROSS JOIN generate_series(1, 20) k WHERE c.email LIKE 'carga%';

INSERT INTO notification (id_workshop, title, message, read_status)
SELECT w.id_workshop, 'Aviso', 'Mensagem ' || k, k % 3 = 0
FROM workshop w CROSS JOIN generate_series(1, 10) k WHERE w.email LIKE 'carga%';

INSERT INTO promotion (id_workshop, id_workshop_service, title, type_discount, discount_value, date_start, date_end)
SELECT ws.id_workshop, ws.id_workshop_service, 'Oferta', 'percentage', 10, NOW() - interval '1 day', NOW() + interval '10 days'
FROM workshop_service ws WHERE ws.id_workshop % 4 = 0;
"""  # noqa: S608 — interpola só a constante N (sem entrada externa)


def _seed():
    with connection.cursor() as cursor:
        for table in TRIGGERS_OFF:
            cursor.execute(
                f"ALTER TABLE {table} DISABLE TRIGGER USER"
            )  # sql-safe: nomes fixos
        cursor.execute(SEED)
        for table in TRIGGERS_OFF:
            cursor.execute(
                f"ALTER TABLE {table} ENABLE TRIGGER USER"
            )  # sql-safe: nomes fixos
        cursor.execute("ANALYZE")
        cursor.execute(
            "SELECT id_client FROM client WHERE email = 'carga1@cliente.test'"
        )
        (client_id,) = cursor.fetchone()
        cursor.execute(
            "SELECT id_workshop FROM chat WHERE id_client = %s LIMIT 1", [client_id]
        )
        (workshop_id,) = cursor.fetchone()
        cursor.execute(
            "SELECT id_chat FROM chat WHERE id_client = %s LIMIT 1", [client_id]
        )
        (chat_id,) = cursor.fetchone()
        cursor.execute(
            "SELECT relname, reltuples FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
        )
        sizes = dict(cursor.fetchall())
    return client_id, workshop_id, chat_id, sizes


def _plans(sql):
    with connection.cursor() as cursor:
        cursor.execute(
            "EXPLAIN (ANALYZE, FORMAT JSON) " + sql
        )  # sql-safe: SQL capturado do próprio ORM
        return cursor.fetchone()[0][0]


def _seq_scans(node, found):
    if node.get("Node Type") == "Seq Scan":
        found.append(node.get("Relation Name"))
    for child in node.get("Plans", []):
        _seq_scans(child, found)
    return found


def test_critical_queries_use_indexes_with_volume(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apps.accounts.models import Client, Workshop

    # "Aberto agora" numa segunda às 10h: o caso mais pesado (quase toda oficina aberta).
    monday_10 = datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    monkeypatch.setattr("apps.workshops.domain.business_now", lambda: monday_10)

    client_id, workshop_id, chat_id, sizes = _seed()
    big = {name for name, rows in sizes.items() if rows >= BIG_TABLE_ROWS}
    assert {"message", "notification", "attendance", "budget", "review"} <= big, sizes

    client = open_account_session(Client.objects.get(pk=client_id), "client")
    workshop = open_account_session(Workshop.objects.get(pk=workshop_id), "workshop")
    visitor = APIClient()
    routes = [
        (
            "mapa (raio 10 km)",
            visitor,
            "/api/map/points/?lat=-5.09&lng=-42.80&radius_km=10",
        ),
        (
            "mapa (busca + aberto agora)",
            visitor,
            "/api/map/points/?lat=-5.09&lng=-42.80&radius_km=30&q=oficina&open_now=true",
        ),
        ("perfil público (nota média)", visitor, f"/api/workshops/{workshop_id}/"),
        ("avaliações públicas", visitor, f"/api/workshops/{workshop_id}/reviews/"),
        ("vitrine", visitor, "/api/promotions/?active=true"),
        ("lista de chats (cliente)", client, "/api/chats/"),
        ("lista de chats (oficina)", workshop, "/api/chats/"),
        (
            "polling de mensagens",
            client,
            f"/api/chats/{chat_id}/messages/?after=2026-01-01T00:00:00Z",
        ),
        ("detalhe do chat", client, f"/api/chats/{chat_id}/"),
        ("não lidas (cliente)", client, "/api/notifications/unread-count/"),
        ("não lidas (oficina)", workshop, "/api/notifications/unread-count/"),
        ("notificações", client, "/api/notifications/"),
        ("favoritos", client, "/api/favorites/"),
        ("atendimentos do cliente", client, "/api/attendances/"),
        ("quadro da oficina", workshop, "/api/workshop/attendances/"),
        ("avaliações recebidas", workshop, "/api/workshop/reviews/"),
        ("clientes atendidos", workshop, "/api/workshop/clients/"),
    ]

    offenders, report = [], []
    for name, api, url in routes:
        with CaptureQueriesContext(connection) as captured:
            response = api.get(url)
        assert response.status_code == 200, (url, response.content[:200])
        total_ms = 0.0
        for query in captured.captured_queries:
            sql = query["sql"]
            if not sql.lstrip().upper().startswith("SELECT"):
                continue
            plan = _plans(sql)
            total_ms += plan["Execution Time"]
            scans = [rel for rel in _seq_scans(plan["Plan"], []) if rel in big]
            if scans:
                offenders.append(
                    f"{name}: Seq Scan em {sorted(set(scans))}\n    {sql[:300]}"
                )
        report.append(
            {
                "rota": name,
                "url": url,
                "consultas": len(captured),
                "execucao_ms": round(total_ms, 2),
            }
        )

    if os.environ.get("SAM_PERF_REPORT"):
        with open(os.environ["SAM_PERF_REPORT"], "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "tabelas": {k: int(v) for k, v in sizes.items() if v > 0},
                    "rotas": report,
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )

    assert not offenders, "varredura sequencial em tabela grande:\n" + "\n".join(
        offenders
    )


def test_plan_walker_sees_sequential_scans():
    """Guarda do próprio verificador: tabela pequena sem filtro → Seq Scan encontrado."""
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (FORMAT JSON) SELECT * FROM service_category")
        plan = cursor.fetchone()[0][0]
    assert _seq_scans(plan["Plan"], []) == ["service_category"]
