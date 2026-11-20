"""BE-083 — Carga do polling do frontend (sem k6/locust: só a biblioteca padrão).

Simula o que as telas logadas fazem de verdade:

* chat aberto (`chat.js`): a cada 5 s, `GET /chats/{id}/messages/?after=…`,
  `GET /chats/{id}/` e `GET /chats/`;
* sino (`components.js`): a cada 60 s, `GET /notifications/unread-count/`.

Uso (banco descartável, nunca o de desenvolvimento):

    # 1) banco migrado e com volume (as mesmas 2.000 oficinas/clientes do teste de
    #    planos + 1 cliente com 100 conversas); senha de todos: SenhaCarga123
    DATABASE_URL=postgres://…/sam_perf DJANGO_SETTINGS_MODULE=config.settings.dev \\
        python tests/perf/polling_load.py seed

    # 2) API como em produção (gunicorn) e a carga
    python tests/perf/polling_load.py run --base-url http://127.0.0.1:8765 \\
        --users 200 --duration 120 > relatorio.json

O relatório traz, por rota: requisições, erros, p50/p95/p99/máx em ms e vazão.
Medições e metas: `backend/docs/adr/0023-nota-media-e-desempenho.md`.
"""

import argparse
import http.client
import json
import os
import random
import statistics
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

PASSWORD = "SenhaCarga123"
HEAVY_EMAIL = "carga1@cliente.test"  # cliente com 100 conversas


# --------------------------------------------------------------------- carga


def seed():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()
    from django.contrib.auth.hashers import make_password
    from django.db import connection, transaction

    from tests.perf.test_query_plans import SEED, TRIGGERS_OFF

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM client WHERE email LIKE 'carga%%'")
        if cursor.fetchone()[0]:
            print("já semeado", file=sys.stderr)
            return
        for table in TRIGGERS_OFF:
            cursor.execute(
                f"ALTER TABLE {table} DISABLE TRIGGER USER"
            )  # sql-safe: nomes fixos
        cursor.execute(SEED)
        # Cliente pesado: 100 conversas com 20 mensagens cada (critério do BE-083).
        cursor.execute(
            """
            WITH heavy AS (SELECT id_client FROM client WHERE email = %s),
                 targets AS (SELECT id_workshop FROM workshop WHERE email LIKE 'carga%%'
                             AND id_workshop NOT IN (SELECT id_workshop FROM chat WHERE id_client = (SELECT id_client FROM heavy))
                             ORDER BY id_workshop LIMIT 99)
            INSERT INTO chat (id_client, id_workshop) SELECT (SELECT id_client FROM heavy), id_workshop FROM targets
            """,
            [HEAVY_EMAIL],
        )
        cursor.execute(
            """
            INSERT INTO message (id_chat, id_client, id_workshop, content, date_sent)
            SELECT ch.id_chat, CASE WHEN k %% 2 = 0 THEN ch.id_client END, CASE WHEN k %% 2 = 1 THEN ch.id_workshop END,
                   'Mensagem ' || k, NOW() - (k || ' minutes')::interval
            FROM chat ch CROSS JOIN generate_series(1, 20) k
            WHERE ch.id_client = (SELECT id_client FROM client WHERE email = %s)
              AND NOT EXISTS (SELECT 1 FROM message m WHERE m.id_chat = ch.id_chat)
            """,
            [HEAVY_EMAIL],
        )
        for table in TRIGGERS_OFF:
            cursor.execute(
                f"ALTER TABLE {table} ENABLE TRIGGER USER"
            )  # sql-safe: nomes fixos
        cursor.execute(
            "UPDATE client SET password_hash = %s WHERE email LIKE 'carga%%'",
            [make_password(PASSWORD)],
        )
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE")
    print("semeado", file=sys.stderr)


# --------------------------------------------------------------------- carga


class User:
    def __init__(self, base, email):
        parts = urlsplit(base)
        self.host, self.port = parts.hostname, parts.port or 80
        self.email = email
        self.cookies = {}
        self.conn = None

    def _connection(self):
        if self.conn is None:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        return self.conn

    def request(self, method, path, body=None):
        headers = {"Accept": "application/json"}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method != "GET":
            headers["Content-Type"] = "application/json"
            headers["X-CSRFToken"] = self.cookies.get("csrftoken", "")
        payload = json.dumps(body) if body is not None else None
        for attempt in (1, 2):
            try:
                conn = self._connection()
                conn.request(method, path, payload, headers)
                response = conn.getresponse()
                data = response.read()
                break
            except (http.client.HTTPException, OSError):
                self.conn = None  # conexão fechada pelo servidor: reabre uma vez
                if attempt == 2:
                    raise
        for header, value in response.getheaders():
            if header.lower() == "set-cookie":
                name, _, rest = value.partition("=")
                self.cookies[name.strip()] = rest.split(";", 1)[0]
        if response.getheader("Connection", "").lower() == "close":
            self.conn = None
        return response.status, data

    def login(self):
        self.request("GET", "/api/auth/me/")  # define o csrftoken
        status, _ = self.request(
            "POST",
            "/api/auth/login/",
            {"role": "client", "email": self.email, "password": PASSWORD},
        )
        if status != 200:
            raise RuntimeError(f"login de {self.email}: {status}")
        status, data = self.request("GET", "/api/chats/")
        self.chat = json.loads(data)["results"][0]["id"]


def run(args):
    stats, lock = {}, threading.Lock()
    deadline = (
        None  # definido depois dos logins (Argon2 em centenas de contas leva tempo)
    )

    def record(route, started, status):
        elapsed = (time.perf_counter() - started) * 1000
        with lock:
            entry = stats.setdefault(route, {"lat": [], "errors": 0})
            entry["lat"].append(elapsed)
            if status != 200:
                entry["errors"] += 1

    def timed(user, route, path):
        started = time.perf_counter()
        try:
            status, data = user.request("GET", path)
        except Exception:  # noqa: BLE001 — erro de rede conta como erro da rota
            status, data = 0, b""
        record(route, started, status)
        return status, data

    def behave(user):
        time.sleep(
            random.uniform(0, args.chat_interval)
        )  # usuários não chegam todos juntos
        after = None
        next_bell = time.monotonic()
        while time.monotonic() < deadline:
            cycle = time.monotonic()
            query = f"?after={quote(after)}" if after else ""
            status, data = timed(
                user,
                "GET /chats/{id}/messages/",
                f"/api/chats/{user.chat}/messages/{query}",
            )
            if status == 200:
                results = json.loads(data)["results"]
                if results:
                    after = results[-1]["date_sent"]
            timed(user, "GET /chats/{id}/", f"/api/chats/{user.chat}/")
            timed(user, "GET /chats/", "/api/chats/")
            if time.monotonic() >= next_bell:
                timed(
                    user,
                    "GET /notifications/unread-count/",
                    "/api/notifications/unread-count/",
                )
                next_bell += args.bell_interval
            time.sleep(max(0.0, args.chat_interval - (time.monotonic() - cycle)))

    def behave_heavy(user):
        """Sessões do cliente com 100 conversas: só a lista de chats (sem throttle)."""
        time.sleep(random.uniform(0, args.chat_interval))
        while time.monotonic() < deadline:
            cycle = time.monotonic()
            timed(user, "GET /chats/ (100 conversas)", "/api/chats/")
            time.sleep(max(0.0, args.chat_interval - (time.monotonic() - cycle)))

    users = [
        User(args.base_url, f"carga{i + 2}@cliente.test") for i in range(args.users)
    ]
    heavy = [User(args.base_url, HEAVY_EMAIL) for _ in range(args.heavy_sessions)]
    for user in users + heavy[:1]:
        user.login()
    for user in heavy[
        1:
    ]:  # mesma conta: reaproveita a sessão (o login tem limite por e-mail)
        user.cookies, user.chat = dict(heavy[0].cookies), heavy[0].chat

    started = time.monotonic()
    deadline = started + args.duration
    threads = [
        threading.Thread(target=behave, args=(user,), daemon=True) for user in users
    ]
    threads += [
        threading.Thread(target=behave_heavy, args=(user,), daemon=True)
        for user in heavy
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.monotonic() - started

    def pct(values, p):
        return (
            round(statistics.quantiles(values, n=100, method="inclusive")[p - 1], 1)
            if len(values) > 1
            else values[0]
        )

    report = {
        "usuarios": args.users,
        "sessoes_100_conversas": args.heavy_sessions,
        "duracao_s": round(wall, 1),
        "rotas": {},
    }
    for route, entry in sorted(stats.items()):
        lat = entry["lat"]
        report["rotas"][route] = {
            "requisicoes": len(lat),
            "erros": entry["errors"],
            "rps": round(len(lat) / wall, 1),
            "p50_ms": pct(lat, 50),
            "p95_ms": pct(lat, 95),
            "p99_ms": pct(lat, 99),
            "max_ms": round(max(lat), 1),
        }
    every = [x for entry in stats.values() for x in entry["lat"]]
    report["total"] = {
        "requisicoes": len(every),
        "rps": round(len(every) / wall, 1),
        "p95_ms": pct(every, 95),
        "erros": sum(e["errors"] for e in stats.values()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    load = sub.add_parser("run")
    load.add_argument("--base-url", default="http://127.0.0.1:8765")
    load.add_argument("--users", type=int, default=200)
    load.add_argument("--duration", type=int, default=120)
    load.add_argument("--chat-interval", type=float, default=5.0)
    load.add_argument("--bell-interval", type=float, default=60.0)
    load.add_argument(
        "--heavy-sessions",
        type=int,
        default=10,
        help="sessões do cliente com 100 conversas",
    )
    args = parser.parse_args()
    seed() if args.command == "seed" else run(args)


if __name__ == "__main__":
    main()
