"""BE-086 — Validação de entradas, limites e prevenção de injeção.

* Cada limite de texto (`apps/core/limits.py`): no limite → aceito; um caractere a
  mais → 400 no campo. A tela que envia o campo usa o mesmo `maxlength` (DP-19).
* Busca e filtros: NUL, aspas, curingas e textos enormes em **todo** parâmetro de
  consulta do schema nunca dão 500; injeção clássica não muda o resultado.
* Corpo grande → 413 (JSON e multipart) com CORS; saída sempre JSON com `nosniff`.
"""

import json
from pathlib import Path

import pytest
from apps.core import limits
from apps.core.db_errors import translate_db_error
from apps.core.exceptions import sam_exception_handler
from apps.core.tests.factories import ServiceCategoryFactory, jpeg_upload
from apps.core.tests.world import build_world
from apps.reviews.models import Review
from conftest import open_account_session
from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import DataError
from rest_framework.test import APIClient

from tests.security.test_authz_matrix import operations

pytestmark = pytest.mark.django_db

FRONTEND = Path(settings.BASE_DIR).parent / "frontend"


@pytest.fixture
def world():
    return build_world()


@pytest.fixture
def staff_api(django_user_model):
    api = APIClient()
    api.force_login(
        django_user_model.objects.create_user(
            "mod", "mod@exemplo.com", "x" * 12, is_staff=True
        )
    )
    return api


def _client(world):
    return open_account_session(world.a.client, "client")


def _workshop(world):
    return open_account_session(world.a.workshop, "workshop")


# (nome, perfil, método, url(world), campo, limite, corpo base(world), formato)
TEXT_LIMITS = [
    (
        "mensagem do chat",
        _client,
        "post",
        lambda w: f"/api/chats/{w.a.chat.pk}/messages/",
        "content",
        limits.MESSAGE,
        lambda w: {},
        "json",
    ),
    (
        "pedido do atendimento",
        _client,
        "post",
        lambda w: "/api/attendances/",
        "observations",
        limits.OBSERVATIONS,
        lambda w: {"id_workshop": w.a.workshop.pk, "id_vehicle": w.a.vehicle.pk},
        "json",
    ),
    (
        "notas técnicas",
        _workshop,
        "patch",
        lambda w: f"/api/workshop/attendances/{w.a.attendance.pk}/",
        "observations",
        limits.OBSERVATIONS,
        lambda w: {},
        "json",
    ),
    (
        "avaliação",
        _client,
        "post",
        lambda w: "/api/reviews/",
        "comment",
        limits.REVIEW_COMMENT,
        lambda w: {"id_budget": w.a.delivered_budget.pk, "rating": 4},
        "json",
    ),
    (
        "resposta da oficina",
        _workshop,
        "post",
        lambda w: f"/api/workshop/reviews/{w.a.review.pk}/response/",
        "workshop_response",
        limits.REVIEW_RESPONSE,
        lambda w: {},
        "json",
    ),
    (
        "denúncia",
        _client,
        "post",
        lambda w: "/api/denunciations/",
        "description",
        limits.DENUNCIATION_DESCRIPTION,
        lambda w: {
            "target_type": "promotion",
            "target_id": str(w.b.promotion.pk),
            "reason": "other",
        },
        "json",
    ),
    (
        "informações do veículo",
        _client,
        "patch",
        lambda w: f"/api/vehicles/{w.a.vehicle.pk}/",
        "information",
        limits.VEHICLE_INFORMATION,
        lambda w: {},
        "json",
    ),
    (
        "histórico manual",
        _client,
        "post",
        lambda w: f"/api/vehicles/{w.a.vehicle.pk}/history/",
        "observations",
        limits.HISTORY_OBSERVATIONS,
        lambda w: {
            "service_name": "Troca de óleo",
            "date_maintenance": "2026-01-10T10:00:00Z",
        },
        "json",
    ),
    (
        "página da oficina",
        _workshop,
        "patch",
        lambda w: "/api/workshop/page/",
        "description",
        limits.DESCRIPTION,
        lambda w: {},
        "multipart",
    ),
    (
        "produto",
        _workshop,
        "post",
        lambda w: "/api/workshop/products/",
        "description",
        limits.DESCRIPTION,
        lambda w: {"name": "Filtro", "price": "20.00"},
        "multipart",
    ),
    (
        "promoção",
        _workshop,
        "patch",
        lambda w: f"/api/workshop/promotions/{w.a.promotion.pk}/",
        "description",
        limits.DESCRIPTION,
        lambda w: {},
        "multipart",
    ),
    (
        "serviço personalizado",
        _workshop,
        "post",
        lambda w: "/api/workshop/services/",
        "description_local",
        limits.DESCRIPTION,
        lambda w: {
            "name_local": "Higienização",
            "id_suggested_category": ServiceCategoryFactory().pk,
            "price_base": "50.00",
            "duration_estimate": 30,
        },
        "json",
    ),
    (
        "endereço do ponto",
        _workshop,
        "post",
        lambda w: "/api/workshop/point/",
        "address",
        limits.ADDRESS,
        lambda w: {
            "name": "Oficina A",
            "type": "oficina",
            "latitude": "-5.1",
            "longitude": "-42.8",
        },
        "json",
    ),
    (
        "nova senha",
        _client,
        "post",
        lambda w: "/api/me/password/",
        "new_password",
        limits.PASSWORD,
        lambda w: {"current_password": "SenhaTeste123"},
        "json",
    ),
]


def _text(size):
    return ("Texto 123 " * (size // 10 + 1))[:size]


@pytest.mark.parametrize(
    ("name", "actor", "method", "url", "field", "limit", "base", "fmt"),
    TEXT_LIMITS,
    ids=[case[0] for case in TEXT_LIMITS],
)
def test_text_limit_is_enforced_by_the_server(
    world, name, actor, method, url, field, limit, base, fmt
):
    if field == "comment":  # o atendimento entregue de A volta a aceitar uma avaliação
        Review.objects.filter(budget=world.a.delivered_budget).delete()
    api = actor(world)

    too_long = getattr(api, method)(
        url(world), {**base(world), field: _text(limit + 1)}, format=fmt
    )
    assert too_long.status_code == 400, too_long.content
    assert field in too_long.json()

    at_limit = getattr(api, method)(
        url(world), {**base(world), field: _text(limit)}, format=fmt
    )
    assert at_limit.status_code in (200, 201, 204), at_limit.content


def test_login_and_reset_refuse_oversized_passwords(api_client):
    long = "a1" * limits.PASSWORD
    login = api_client.post(
        "/api/auth/login/",
        {"role": "client", "email": "x@exemplo.com", "password": long},
        format="json",
    )
    assert login.status_code == 400 and "password" in login.json()
    confirm = api_client.post(
        "/api/auth/password-reset/confirm/",
        {"token": "x", "password": long},
        format="json",
    )
    assert confirm.status_code == 400


def test_admin_text_limits(world, staff_api):
    denunciation = world.b.denunciation
    response = staff_api.patch(
        f"/api/admin/denunciations/{denunciation.pk}/",
        {
            "status_denunciation": "dismissed",
            "moderation_decision": _text(limits.MODERATION_DECISION + 1),
        },
        format="json",
    )
    assert response.status_code == 400 and "moderation_decision" in response.json()

    request = world.a.service_request
    response = staff_api.post(
        f"/api/admin/service-requests/{request.pk}/reject/",
        {"motivation": _text(limits.REJECTION_MOTIVATION + 1)},
        format="json",
    )
    assert response.status_code == 400 and "motivation" in response.json()


# Tela → campo: o `maxlength` da tela é o limite do servidor (DP-19).
FRONTEND_MAXLENGTH = [
    ("js/chat.js", 'id="mi"', limits.MESSAGE),
    ("js/attendance-parts.js", "Descreva o problema", limits.OBSERVATIONS),
    ("js/attendance-parts.js", "id: 'comment'", limits.REVIEW_COMMENT),
    ("js/w-attendance.js", "id: 'observations'", limits.OBSERVATIONS),
    ("js/w-reviews.js", "id: 'workshop_response'", limits.REVIEW_RESPONSE),
    ("js/components-parts.js", "id: 'rdesc'", limits.DENUNCIATION_DESCRIPTION),
    ("js/vehicle-new.js", "f('information'", limits.VEHICLE_INFORMATION),
    ("js/vehicle.js", "id: 'hn'", limits.HISTORY_OBSERVATIONS),
    ("js/w-profile.js", "id: 'description'", limits.DESCRIPTION),
    ("js/map.js", 'id="q"', limits.SEARCH),
    ("js/home.js", "Buscar oficina ou serviço", limits.SEARCH),
]


@pytest.mark.parametrize(
    ("path", "needle", "limit"), FRONTEND_MAXLENGTH, ids=lambda v: str(v)
)
def test_frontend_uses_the_same_maxlength(path, needle, limit):
    lines = (FRONTEND / path).read_text(encoding="utf-8").splitlines()
    index = next((i for i, line in enumerate(lines) if needle in line), None)
    assert index is not None, f"{needle!r} não encontrado em {path}"
    window = "\n".join(lines[index : index + 4])
    assert f'maxlength="{limit}"' in window, (
        f"{path}: maxlength diferente de {limit} perto de {needle!r}"
    )


# ------------------------------------------------------------- busca e filtros

INJECTIONS = [
    "' OR 1=1 --",
    "'; DROP TABLE client; --",
    '" OR ""="',
    "%",
    "_",
    "\\",
    "1) OR (1=1",
]


@pytest.mark.parametrize(
    "url", ["/api/services/", "/api/map/points/", "/api/points-of-interest/"]
)
def test_search_refuses_nul_and_oversized_text(world, url):
    api = _workshop(world)
    nul = api.get(url, {"q": "óleo\x00"})
    assert nul.status_code == 400 and nul.json() == {"q": [limits.NUL_MESSAGE]}

    long = api.get(url, {"q": "a" * (limits.SEARCH + 1)})
    assert long.status_code == 400 and "q" in long.json()
    assert api.get(url, {"q": "a" * limits.SEARCH}).status_code == 200


@pytest.mark.parametrize("payload", INJECTIONS)
@pytest.mark.parametrize(
    "url", ["/api/services/", "/api/map/points/", "/api/points-of-interest/"]
)
def test_search_injection_is_just_text(world, url, payload):
    api = _workshop(world)
    everything = api.get(url).json()["count"]
    assert everything > 0

    response = api.get(url, {"q": payload})

    assert response.status_code == 200, response.content
    assert response.json()["count"] < everything, "a busca injetada devolveu tudo"


def _query_params(op):
    from tests.security.test_authz_matrix import openapi

    spec = openapi()["paths"][op.path][op.method.lower()]
    return [p["name"] for p in spec.get("parameters", []) if p["in"] == "query"]


FUZZ = [
    "' OR 1=1 --",
    "\x00",
    "%00",
    "%",
    "-1",
    "9" * 40,
    "2026-13-45T99:99",
    "a" * 5000,
    "[]",
    "{}",
]
GET_OPERATIONS = [op for op in operations() if op.method == "GET" and _query_params(op)]


@pytest.mark.parametrize("op", GET_OPERATIONS, ids=str)
def test_query_parameters_never_cause_server_errors(world, staff_api, op):
    """Todo parâmetro de consulta declarado no schema, com entradas hostis: nunca 500."""
    from tests.security.test_authz_matrix import values_for

    role = (
        sorted(op.allowed - {"visitor", "workshop_new"})[0]
        if op.allowed - {"visitor", "workshop_new"}
        else "visitor"
    )
    api = {
        "admin": staff_api,
        "client": _client(world),
        "workshop": _workshop(world),
        "visitor": APIClient(),
    }[role]
    url = op.url(
        values_for(op, world, "A", role if role in ("client", "workshop") else None)
    )
    for name in _query_params(op):
        for value in FUZZ:
            response = api.get(url, {name: value})
            assert response.status_code < 500, (
                f"{op.key} ?{name}={value[:20]!r}: {response.status_code}"
            )
            assert response["Content-Type"].startswith("application/json")


def test_denunciation_target_id_injection_is_not_found(world):
    response = _client(world).post(
        "/api/denunciations/",
        {"target_type": "review", "target_id": "' OR 1=1 --", "reason": "spam"},
        format="json",
    )
    assert response.status_code in (400, 404)


# ------------------------------------------------------------------ corpo


def test_oversized_json_body_is_413_with_cors(api_client):
    body = json.dumps({"email": "a" * settings.SAM_MAX_BODY_BYTES})
    origin = settings.CORS_ALLOWED_ORIGINS[0]

    response = api_client.generic(
        "POST",
        "/api/auth/login/",
        body,
        content_type="application/json",
        HTTP_ORIGIN=origin,
    )

    assert response.status_code == 413
    assert response["Content-Type"].startswith("application/json")
    assert "detail" in response.json()
    assert response["Access-Control-Allow-Origin"] == origin


def test_oversized_multipart_is_413(world):
    blob = b"0" * (settings.SAM_MAX_UPLOAD_BYTES + 1)
    from django.core.files.uploadedfile import SimpleUploadedFile

    response = _client(world).patch(
        f"/api/vehicles/{world.a.vehicle.pk}/",
        {"photo_1": SimpleUploadedFile("foto.jpg", blob, content_type="image/jpeg")},
        format="multipart",
    )
    assert response.status_code == 413


def test_image_above_its_own_limit_is_400(world, settings):
    settings.SAM_IMAGE_MAX_BYTES = 1000
    response = _client(world).patch(
        f"/api/vehicles/{world.a.vehicle.pk}/",
        {"photo_1": jpeg_upload(size=(400, 400))},
        format="multipart",
    )
    assert response.status_code == 400 and "photo_1" in response.json()


def test_too_many_fields_is_400(world):
    fields = {
        f"campo{i}": "x" for i in range(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS + 1)
    }
    response = _client(world).patch(
        f"/api/vehicles/{world.a.vehicle.pk}/", fields, format="multipart"
    )
    assert response.status_code == 400


def test_invalid_content_length_is_400(api_client):
    response = api_client.generic(
        "POST",
        "/api/auth/login/",
        "{}",
        content_type="application/json",
        CONTENT_LENGTH="x",
    )
    assert response.status_code == 400


def test_safety_nets_turn_payload_and_nul_errors_into_4xx():
    assert sam_exception_handler(RequestDataTooBig("grande"), {}).status_code == 413
    nul = translate_db_error(
        DataError("PostgreSQL text fields cannot contain NUL (0x00) bytes")
    )
    assert nul.status_code == 400 and nul.detail == {"detail": limits.NUL_MESSAGE}


# ------------------------------------------------------------------ saída


@pytest.mark.parametrize(
    ("method", "url", "body", "status"),
    [
        ("GET", "/api/nao-existe/", None, 404),
        ("DELETE", "/api/services/", None, 405),
        ("POST", "/api/auth/login/", "{json quebrado", 400),
        ("GET", "/api/vehicles/", None, 401),
    ],
)
def test_errors_are_json_with_nosniff(api_client, method, url, body, status):
    response = api_client.generic(
        method, url, body or "", content_type="application/json"
    )

    assert response.status_code == status
    assert response["Content-Type"].startswith("application/json")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "detail" in response.json()
