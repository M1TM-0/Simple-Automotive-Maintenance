"""BE-081 — Testes de contrato: respostas reais × schema OpenAPI × normalizadores do frontend.

1. `test_every_operation_answers_as_documented` percorre um fluxo que exercita as 91
   operações do schema (sucesso de cada uma) e valida cada resposta contra o schema em
   modo estrito (`tests/contract/openapi.py`). Ao final, toda operação precisa ter sido
   validada com 2xx — rota nova sem passo no fluxo falha aqui.
2. `test_frontend_normalizers_accept_real_responses` grava respostas reais e roda os
   normalizadores do `frontend/js/api.js` (`normChat`, `normMsg`, `normPromo`,
   `normWorkshop`, `normWAtt`) no Node, conferindo os campos que as telas leem.
"""

import json
import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from apps.accounts.tokens import make_password_reset_token
from apps.core import heartbeat
from apps.core.tests.factories import jpeg_upload
from apps.core.tests.world import build_world
from apps.workshops import overpass
from conftest import open_account_session
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from tests.contract.openapi import COVERAGE, VIOLATIONS, ContractClient, all_operations

pytestmark = pytest.mark.django_db

API_JS = Path(settings.BASE_DIR).parent / "frontend" / "js" / "api.js"
RUNNER = Path(__file__).with_name("normalizers.js")
PASSWORD = "SenhaTeste123"


def _iso(delta):
    return (timezone.now() + delta).isoformat()


@pytest.fixture
def actors(django_user_model):
    world = build_world()
    staff = django_user_model.objects.create_user(
        "moderador", "mod@exemplo.com", "x" * 12, is_staff=True
    )
    admin = APIClient()
    admin.force_login(staff)
    return world, {
        "visitor": ContractClient(APIClient()),
        "client": ContractClient(open_account_session(world.a.client, "client")),
        "workshop": ContractClient(open_account_session(world.a.workshop, "workshop")),
        "workshop_b": ContractClient(
            open_account_session(world.b.workshop, "workshop")
        ),
        "admin": ContractClient(admin),
    }


def _public(world, visitor):
    workshop = world.a.workshop.pk
    visitor.get("/api/health/")
    visitor.get("/api/health/ready/")
    heartbeat.record_success(heartbeat.EXPIRATION)  # rotina "rodou agora" (BE-092)
    visitor.get("/api/health/jobs/")
    visitor.get("/api/service-categories/")
    visitor.get("/api/services/", {"q": "óleo"})
    visitor.get(
        "/api/map/points/", {"lat": "-5.0912", "lng": "-42.8031", "radius_km": "50"}
    )
    # Segunda fonte do mapa (BE-094): Overpass simulada, com um ponto de cada forma.
    elements = [
        {
            "type": "node",
            "id": 1,
            "lat": -5.08,
            "lon": -42.82,
            "tags": {"amenity": "fuel", "name": "Posto", "addr:street": "Rua A"},
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": -5.07, "lon": -42.83},
            "tags": {"shop": "tyres"},
        },
    ]
    fake_url = {**settings.SAM_OVERPASS, "URL": "https://overpass.test/api/interpreter"}
    with (
        override_settings(SAM_OVERPASS=fake_url),
        mock.patch.object(overpass, "_fetch", return_value=elements),
    ):
        visitor.get(
            "/api/map/external-points/",
            {
                "south": "-5.095",
                "west": "-42.845",
                "north": "-5.055",
                "east": "-42.805",
            },
        )
    visitor.get("/api/promotions/", {"active": "true"})
    visitor.get(f"/api/workshops/{workshop}/")
    visitor.get(f"/api/workshops/{workshop}/products/")
    visitor.get(f"/api/workshops/{workshop}/promotions/")
    visitor.get(f"/api/workshops/{workshop}/reviews/")


def _accounts(world):
    client = ContractClient(APIClient())
    client.post(
        "/api/auth/register/",
        {
            "role": "client",
            "name": "Bia Souza",
            "email": "bia@exemplo.com",
            "password": PASSWORD,
        },
    )
    client.get("/api/auth/me/")
    client.patch("/api/me/", {"name": "Beatriz Souza", "phone_number": "86999990000"})
    client.post(
        "/api/me/password/",
        {"current_password": PASSWORD, "new_password": "OutraSenha456"},
        expect=204,
    )
    client.post("/api/auth/logout/", expect=204)
    client.post(
        "/api/auth/login/",
        {"role": "client", "email": "bia@exemplo.com", "password": "OutraSenha456"},
        expect=200,
    )

    workshop = ContractClient(APIClient())
    workshop.post(
        "/api/auth/register/",
        {
            "role": "workshop",
            "name_fantasy": "Oficina Nova",
            "name_responsible": "Carlos",
            "cnpj": "11222333000181",
            "email": "nova@exemplo.com",
            "password": PASSWORD,
        },
    )

    visitor = ContractClient(APIClient())
    # Conta do lado B: redefinir a senha derruba as sessões da conta (P-03).
    visitor.post(
        "/api/auth/password-reset/", {"email": world.b.client.email}, expect=204
    )
    token = make_password_reset_token("client", world.b.client)
    visitor.post(
        "/api/auth/password-reset/confirm/",
        {"token": token, "password": "NovaSenha789"},
        expect=204,
    )


def _client_side(world, client):
    b_workshop = world.b.workshop.pk
    client.get("/api/favorites/")
    client.post("/api/favorites/", {"id_workshop": b_workshop})
    client.delete(f"/api/favorites/{b_workshop}/")

    body = {
        "brand": "Fiat",
        "model": "Argo",
        "year_fabrication": "2020",
        "year_model": "2021",
        "plate": "QWE1R23",
        "fuel": "flex",
        "exchange": "manual",
        "mileage_km": "41000",
        "photo_1": jpeg_upload(),
    }
    vehicle = client.post("/api/vehicles/", body, fmt="multipart").json()["id"]
    client.get("/api/vehicles/")
    client.get(f"/api/vehicles/{vehicle}/")
    client.patch(f"/api/vehicles/{vehicle}/", {"color": "Azul", "history_shared": True})
    record = client.post(
        f"/api/vehicles/{vehicle}/history/",
        {
            "service_name": "Troca de óleo",
            "date_maintenance": _iso(-timedelta(days=200)),
            "mileage_km": 35000,
            "interval_km": 10000,
            "observations": "Óleo 5W30",
        },
    ).json()["id"]
    client.get(f"/api/vehicles/{vehicle}/history/")
    client.get(f"/api/vehicles/{vehicle}/history/{record}/")
    client.get(f"/api/vehicles/{vehicle}/upcoming-maintenance/")
    spare = client.post(
        "/api/vehicles/",
        {**body, "plate": "RTY4U56", "photo_1": jpeg_upload()},
        fmt="multipart",
    ).json()["id"]
    client.delete(f"/api/vehicles/{spare}/")

    data = {
        "id_workshop": world.a.workshop.pk,
        "id_vehicle": world.a.vehicle.pk,
        "observations": "Barulho na suspensão",
    }
    attendance = client.post("/api/attendances/", data).json()["id"]
    canceled = client.post("/api/attendances/", data).json()["id"]
    client.get("/api/attendances/")
    client.get(f"/api/attendances/{attendance}/")
    client.post(f"/api/attendances/{canceled}/cancel/", expect=200)
    client.post(f"/api/budgets/{world.a.budget.pk}/approve/", expect=200)
    return attendance


def _budget_round(workshop, attendance, service_id):
    budget = workshop.post(
        f"/api/workshop/attendances/{attendance}/budget/", {}
    ).json()["id"]
    item = workshop.post(
        f"/api/workshop/budgets/{budget}/items/",
        {
            "item_type": "service",
            "id_workshop_service": service_id,
            "description": "Revisão",
            "quantity": "1",
            "unit_price": "150.00",
        },
    ).json()["id"]
    workshop.post(f"/api/workshop/budgets/{budget}/send/", expect=200)
    return budget, item


def _workshop_side(world, workshop, client, attendance):
    service_id = world.a.workshop_service.pk
    workshop.get("/api/workshop/attendances/")
    workshop.get(f"/api/workshop/attendances/{attendance}/")
    workshop.patch(
        f"/api/workshop/attendances/{attendance}/",
        {"observations": "Bucha gasta", "mileage_km": 52000},
    )

    # 1º orçamento: edição, itens, envio e recusa do cliente.
    budget = workshop.post(
        f"/api/workshop/attendances/{attendance}/budget/", {}
    ).json()["id"]
    workshop.patch(
        f"/api/workshop/budgets/{budget}/",
        {"observations": "Peças originais", "date_validity": _iso(timedelta(days=5))},
    )
    labor = workshop.post(
        f"/api/workshop/budgets/{budget}/items/",
        {
            "item_type": "labor",
            "description": "Mão de obra",
            "quantity": "2",
            "unit_price": "60.00",
        },
    ).json()["id"]
    workshop.patch(
        f"/api/workshop/budgets/{budget}/items/{labor}/", {"unit_price": "65.00"}
    )
    workshop.delete(f"/api/workshop/budgets/{budget}/items/{labor}/")
    workshop.post(
        f"/api/workshop/budgets/{budget}/items/",
        {
            "item_type": "service",
            "id_workshop_service": service_id,
            "description": "Troca de buchas",
            "quantity": "1",
            "unit_price": "180.00",
        },
    )
    workshop.post(f"/api/workshop/budgets/{budget}/send/", expect=200)
    client.post(f"/api/budgets/{budget}/reject/", expect=200)

    # 2º orçamento: aprovação, execução, conclusão e entrega.
    budget, item = _budget_round(workshop, attendance, service_id)
    client.post(f"/api/budgets/{budget}/approve/", expect=200)
    workshop.post(
        f"/api/workshop/attendances/{attendance}/transition/",
        {"status": "in_progress"},
        expect=200,
    )
    workshop.patch(
        f"/api/workshop/budgets/{budget}/items/{item}/execution/",
        {"execution_status": "executed"},
    )
    workshop.post(
        f"/api/workshop/attendances/{attendance}/transition/",
        {"status": "completed"},
        expect=200,
    )
    workshop.post(
        f"/api/workshop/attendances/{attendance}/transition/",
        {"status": "delivered"},
        expect=200,
    )

    review = client.post(
        "/api/reviews/", {"id_budget": budget, "rating": 5, "comment": "Ótimo"}
    ).json()["id"]
    workshop.post(
        f"/api/workshop/reviews/{review}/response/",
        {"workshop_response": "Obrigado!"},
        expect=200,
    )
    workshop.get("/api/workshop/reviews/")
    workshop.get("/api/workshop/clients/")
    workshop.get(f"/api/workshop/clients/{world.a.client.pk}/vehicles/")
    workshop.get(f"/api/workshop/vehicles/{world.a.vehicle.pk}/history/")


def _workshop_setup(world, workshop):
    workshop.get("/api/workshop/me/")
    workshop.patch("/api/workshop/me/", {"phone_number": "8633334444"})
    workshop.patch(
        "/api/workshop/page/",
        {"description": "Desde 1998.", "photo_banner": jpeg_upload()},
        fmt="multipart",
    )
    workshop.get("/api/workshop/operation-hours/")
    workshop.put(
        "/api/workshop/operation-hours/",
        [
            {"day_of_week": 1, "opening_time": "08:00", "closing_time": "12:00"},
            {"day_of_week": 1, "opening_time": "13:00", "closing_time": "18:00"},
        ],
    )
    workshop.get("/api/points-of-interest/", {"q": "oficina"})
    workshop.post(
        "/api/workshop/point/",
        {
            "name": "Oficina A (nova sede)",
            "type": "oficina",
            "latitude": "-5.0950",
            "longitude": "-42.8100",
            "address": "Rua das Flores, 10",
        },
        expect=200,
    )
    workshop.get("/api/workshop/services/")
    workshop.post(
        "/api/workshop/services/",
        {
            "name_local": "Higienização de ar",
            "id_suggested_category": world.a.service_request.suggested_category_id,
            "price_base": "120.00",
            "duration_estimate": 40,
        },
    )
    workshop.patch(
        f"/api/workshop/services/{world.a.workshop_service.pk}/",
        {"price_base": "130.00"},
    )
    workshop.get("/api/workshop/products/")
    product = workshop.post(
        "/api/workshop/products/",
        {"name": "Filtro de ar", "price": "35.00", "photo": jpeg_upload()},
        fmt="multipart",
    ).json()["id"]
    workshop.patch(
        f"/api/workshop/products/{product}/", {"active": "false"}, fmt="multipart"
    )

    workshop.get("/api/workshop/promotions/")
    promotion = workshop.post(
        "/api/workshop/promotions/",
        {
            "title": "Revisão de inverno",
            "type_discount": "percentage",
            "discount_value": "15",
            "date_start": _iso(timedelta(0)),
            "date_end": _iso(timedelta(days=20)),
            "id_workshop_service": world.a.workshop_service.pk,
            "image": jpeg_upload(),
        },
        fmt="multipart",
    ).json()["id"]
    workshop.patch(
        f"/api/workshop/promotions/{promotion}/",
        {"discount_value": "20"},
        fmt="multipart",
    )
    workshop.get(f"/api/workshop/promotions/{promotion}/advertisements/")
    workshop.post(
        f"/api/workshop/promotions/{promotion}/advertisements/",
        {
            "image": jpeg_upload(),
            "date_start": _iso(timedelta(days=1)),
            "date_end": _iso(timedelta(days=4)),
        },
        fmt="multipart",
    )


def _chat_and_notifications(world, client, workshop):
    client.get("/api/chats/")
    client.post(f"/api/chats/{world.a.workshop.pk}/open/", expect=200)  # já existe
    client.post(f"/api/chats/{world.b.workshop.pk}/open/", expect=201)
    chat = world.a.chat.pk
    client.get(f"/api/chats/{chat}/")
    client.get(f"/api/chats/{chat}/messages/")
    client.post(f"/api/chats/{chat}/messages/", {"content": "Posso levar amanhã?"})
    client.post(f"/api/chats/{chat}/read/", expect=204)
    workshop.get("/api/chats/")
    workshop.get(f"/api/chats/{chat}/")
    workshop.get(f"/api/workshop/attendances/{world.a.attendance.pk}/")

    client.post(
        "/api/denunciations/",
        {
            "target_type": "review",
            "target_id": str(world.b.review.pk),
            "reason": "spam",
        },
    )
    client.get("/api/notifications/")
    client.get("/api/notifications/unread-count/")
    client.post(
        f"/api/notifications/{world.a.notification_client.pk}/read/", expect=204
    )
    client.post("/api/notifications/read-all/", expect=204)


def _moderation(world, admin):
    admin.get("/api/admin/denunciations/")
    admin.get(f"/api/admin/denunciations/{world.b.denunciation.pk}/")
    admin.patch(
        f"/api/admin/denunciations/{world.b.denunciation.pk}/",
        {"status_denunciation": "in_review"},
    )
    admin.post(f"/api/admin/reviews/{world.b.review.pk}/hide/", expect=200)
    admin.get("/api/admin/service-requests/")
    admin.post(
        f"/api/admin/service-requests/{world.a.service_request.pk}/approve/",
        {},
        expect=200,
    )
    admin.post(
        f"/api/admin/service-requests/{world.b.service_request.pk}/reject/",
        {"motivation": "Duplicado"},
        expect=200,
    )


def test_every_operation_answers_as_documented(actors):
    world, c = actors
    COVERAGE.clear()
    VIOLATIONS.clear()

    _public(world, c["visitor"])
    _accounts(world)
    attendance = _client_side(world, c["client"])
    _workshop_side(world, c["workshop"], c["client"], attendance)
    _workshop_setup(world, c["workshop"])
    _chat_and_notifications(world, c["client"], c["workshop"])
    _moderation(world, c["admin"])

    assert not VIOLATIONS, "respostas fora do schema:\n" + "\n".join(VIOLATIONS)
    missing = sorted(f"{m} {p}" for m, p in all_operations() - COVERAGE)
    assert not missing, (
        "operações sem resposta 2xx validada no fluxo de contrato: "
        + ", ".join(missing)
    )


# ------------------------------------------------------------ normalizadores


def _jobs(world, c):
    """Grava respostas reais e monta os jobs do runner Node."""
    chat, workshop = world.a.chat.pk, world.a.workshop.pk
    client, ws, visitor = c["client"], c["workshop"], c["visitor"]
    client.post(f"/api/chats/{chat}/messages/", {"content": "Combinado!"})
    client.get("/api/chats/")
    client.get(f"/api/chats/{chat}/")
    client.get(f"/api/chats/{chat}/messages/")
    client.post(f"/api/chats/{workshop}/open/", expect=200)
    client.get("/api/notifications/unread-count/")
    ws.get("/api/chats/")
    ws.get(f"/api/chats/{chat}/messages/")
    ws.get(f"/api/workshop/attendances/{world.a.attendance.pk}/")
    visitor.get("/api/promotions/", {"active": "true"})
    visitor.get(f"/api/workshops/{workshop}/")
    visitor.get(f"/api/workshops/{workshop}/promotions/")

    def job(name, role, call, args, recorder):
        return {
            "name": name,
            "role": role,
            "call": call,
            "args": args,
            "responses": {key: rec["body"] for key, rec in recorder.recorded.items()},
        }

    return [
        job("chats.list[client]", "client", "chats.list", [], client),
        job("chats.get", "client", "chats.get", [chat], client),
        job("chats.open", "client", "chats.open", [workshop], client),
        job("chats.messages[client]", "client", "chats.messages", [chat], client),
        job("chats.send", "client", "chats.send", [chat, "Combinado!"], client),
        job(
            "notifications.unreadCount",
            "client",
            "notifications.unreadCount",
            [],
            client,
        ),
        job("chats.list[workshop]", "workshop", "chats.list", [], ws),
        job("chats.messages[workshop]", "workshop", "chats.messages", [chat], ws),
        job(
            "workshop.attendance",
            "workshop",
            "workshop.attendance",
            [world.a.attendance.pk],
            ws,
        ),
        job("promotions.active", "client", "promotions.active", [], visitor),
        job("workshops.get", "client", "workshops.get", [workshop], visitor),
        job(
            "workshops.promotions",
            "client",
            "workshops.promotions",
            [workshop],
            visitor,
        ),
    ]


@pytest.mark.skipif(
    shutil.which("node") is None
    and not os.environ.get("CI"),  # no CI a falta do Node é erro
    reason="Node.js não instalado",
)
def test_frontend_normalizers_accept_real_responses(actors, tmp_path):
    world, c = actors
    VIOLATIONS.clear()
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps(_jobs(world, c)), encoding="utf-8")

    run = subprocess.run(
        ["node", str(RUNNER), str(API_JS), str(jobs_file)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    failed = {name: result["error"] for name, result in out.items() if not result["ok"]}
    assert not failed, failed
    v = {name: result["value"] for name, result in out.items()}

    # normChat: interlocutor, não lidas e última mensagem.
    [row] = [
        r for r in v["chats.list[client]"]["results"] if r["id"] == world.a.chat.pk
    ]
    assert row["name"] == world.a.workshop.name_fantasy
    assert row["workshop_id"] == world.a.workshop.pk
    assert isinstance(row["unread"], int) and row["unread"] >= 0
    assert row["last_message"] == "Combinado!" and row["last_at"]
    [row] = v["chats.list[workshop]"]["results"]
    assert row["name"] == world.a.client.name and isinstance(row["unread"], int)
    for name in ("chats.get", "chats.open"):
        assert (
            v[name]["id"] == world.a.chat.pk
            and v[name]["name"] == world.a.workshop.name_fantasy
        )

    # normMsg: `mine` pelo remetente × perfil logado, conteúdo, data e status.
    for role in ("client", "workshop"):
        messages = v[f"chats.messages[{role}]"]["results"]
        assert {m["mine"] for m in messages} == {True, False}
        assert all(
            m["content"] and m["at"] and m["status"] in ("sent", "delivered", "read")
            for m in messages
        )
        assert all(isinstance(m["id"], int) for m in messages)
    assert (
        v["chats.send"]["mine"] is True and v["chats.send"]["content"] == "Combinado!"
    )
    assert isinstance(v["notifications.unreadCount"], int)

    # normPromo: tipo, título, oficina e vigência.
    for name in ("promotions.active", "workshops.promotions"):
        promos = v[name]["results"]
        assert promos, name
        for promo in promos:
            assert promo["kind"] in ("promotion", "advertisement")
            assert promo["title"] and promo["valid"] is True
            assert isinstance(promo["workshop_id"], int) and promo["workshop_name"]
            assert (
                promo["type_discount"] in ("percentage", "fixed")
                and promo["discount_value"]
            )

    # normWorkshop: campos planos que T06 lê.
    shop = v["workshops.get"]
    assert shop["name_fantasy"] == world.a.workshop.name_fantasy
    assert isinstance(shop["description"], str) and isinstance(shop["address"], str)
    assert isinstance(shop["latitude"], float) and isinstance(shop["longitude"], float)
    assert shop["operation_hours"] and shop["services"]
    assert "cnpj" not in shop and "email" not in shop

    # normWAtt: notas técnicas na tela, pedido do cliente preservado.
    attendance = v["workshop.attendance"]
    assert attendance["observations"] == world.a.attendance.technical_notes
    assert attendance["client_observations"] == world.a.attendance.observations
