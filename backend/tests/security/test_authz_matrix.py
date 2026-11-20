"""BE-084 — Matriz de autorização (BOLA/IDOR) derivada do schema OpenAPI.

Para **cada operação** do schema (gerado na hora pelo drf-spectacular), os casos são
montados sem código adicional:

* a política esperada vem das `permission_classes` da view (e é conferida contra a
  matriz da seção 8 do backlog em `CONTRACT`);
* visitante → **401** (`WWW-Authenticate: Session`); perfil errado → **403**;
* recurso de outro dono → **404**: o cliente/oficina A chama a rota com os ids do
  lado B do mundo de teste (`apps/core/tests/world.py`); os dados de B não mudam e,
  como controle positivo, o próprio B não recebe 401/403/404 na mesma chamada;
* nenhuma leitura dada a A (nem leitura pública sobre B) contém o marcador
  `SEGREDO-B` dos campos privados de B;
* nenhum corpo de requisição aceita dono, status ou valores calculados
  (`REQUEST_FIELD_ALLOWLIST` lista as exceções do contrato).

Rota nova: os testes de 401/403 nascem sozinhos; o de 404 resolve os parâmetros de
caminho pelo nome (`id_<entidade>`, `<entidade>_id` ou `{id}` + segmento anterior).
Nome de parâmetro desconhecido falha com a instrução do que acrescentar.
A lista de verificação para revisão de endpoints novos está em
`backend/docs/seguranca/checklist-endpoints.md`.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from functools import cache

import pytest
from apps.accounts.models import Client, Favorite, Workshop
from apps.attendances.models import Attendance, Budget, BudgetItem
from apps.catalog.models import Product, WorkshopService
from apps.chat.models import Chat, Message
from apps.core import heartbeat
from apps.core.permissions import (
    IsAccountHolder,
    IsChatParticipant,
    IsClient,
    IsWorkshop,
    IsWorkshopSetupComplete,
)
from apps.core.permissions import IsAdmin as CoreIsAdmin
from apps.core.tests.factories import (
    AttendanceFactory,
    ChatFactory,
    ClientFactory,
    MessageFactory,
    NotificationFactory,
    PagWorkshopFactory,
    jpeg_upload,
    make_ready_workshop,
)
from apps.core.tests.world import build_world
from apps.moderation.permissions import IsAdmin as ModerationIsAdmin
from apps.notifications.models import Notification
from apps.promotions.models import Promotion, PromotionAdvertisement
from apps.reviews.models import Denunciation, Review
from apps.vehicles.models import RegisterMaintenance, Vehicle
from conftest import open_account_session
from django.db import connection
from django.urls import resolve
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

METHODS = ("get", "post", "put", "patch", "delete")
ROLES = ("visitor", "client", "workshop", "workshop_new", "admin")

# Quem passa por cada política (workshop_new = oficina sem cadastro concluído).
ALLOWED = {
    "public": set(ROLES),
    "authenticated": {"client", "workshop", "workshop_new", "admin"},
    "account": {"client", "workshop", "workshop_new"},
    "client": {"client"},
    "workshop": {"workshop", "workshop_new"},
    "workshop_ready": {"workshop"},
    "admin": {"admin"},
}

# ------------------------------------------------------------------ contrato
# Matriz da seção 8 do backlog (colunas Autenticação/Permissão) + infraestrutura
# (8.11). "workshop" = rotas do assistente T17; "workshop_ready" = demais `/workshop/*`.
_W = "workshop_ready"
CONTRACT = {
    # 8.1 accounts
    "POST /api/auth/register/": "public",
    "POST /api/auth/login/": "public",
    "POST /api/auth/logout/": "authenticated",
    "GET /api/auth/me/": "public",
    "POST /api/auth/password-reset/": "public",
    "POST /api/auth/password-reset/confirm/": "public",
    "PATCH /api/me/": "account",
    "POST /api/me/password/": "account",
    "GET /api/favorites/": "client",
    "POST /api/favorites/": "client",
    "DELETE /api/favorites/{id_workshop}/": "client",
    # 8.2 catalog
    "GET /api/service-categories/": "public",
    "GET /api/services/": "public",
    "GET /api/workshops/{workshop_id}/products/": "public",
    "GET /api/workshop/services/": "workshop",
    "POST /api/workshop/services/": "workshop",
    "PATCH /api/workshop/services/{id_workshop_service}/": "workshop",
    "GET /api/workshop/products/": _W,
    "POST /api/workshop/products/": _W,
    "PATCH /api/workshop/products/{id_product}/": _W,
    # 8.3 workshops
    "GET /api/map/points/": "public",
    "GET /api/map/external-points/": "public",  # BE-094: OpenStreetMap (Overpass)
    "GET /api/points-of-interest/": "workshop",
    "GET /api/workshops/{id}/": "public",
    "GET /api/workshop/me/": "workshop",
    "PATCH /api/workshop/me/": "workshop",
    "PATCH /api/workshop/page/": "workshop",
    "GET /api/workshop/operation-hours/": "workshop",
    "PUT /api/workshop/operation-hours/": "workshop",
    "POST /api/workshop/point/": "workshop",
    # 8.4 vehicles
    "GET /api/vehicles/": "client",
    "POST /api/vehicles/": "client",
    "GET /api/vehicles/{id_vehicle}/": "client",
    "PATCH /api/vehicles/{id_vehicle}/": "client",
    "DELETE /api/vehicles/{id_vehicle}/": "client",
    "GET /api/vehicles/{id_vehicle}/history/": "client",
    "POST /api/vehicles/{id_vehicle}/history/": "client",
    "GET /api/vehicles/{id_vehicle}/history/{record}/": "client",
    "GET /api/vehicles/{id_vehicle}/upcoming-maintenance/": "client",
    # 8.5 attendances
    "POST /api/attendances/": "client",
    "GET /api/attendances/": "client",
    "GET /api/attendances/{id_attendance}/": "client",
    "POST /api/attendances/{id_attendance}/cancel/": "client",
    "POST /api/budgets/{id}/approve/": "client",
    "POST /api/budgets/{id}/reject/": "client",
    "GET /api/workshop/attendances/": _W,
    "GET /api/workshop/attendances/{id_attendance}/": _W,
    "PATCH /api/workshop/attendances/{id_attendance}/": _W,
    "POST /api/workshop/attendances/{id_attendance}/transition/": _W,
    "POST /api/workshop/attendances/{id_attendance}/budget/": _W,
    "PATCH /api/workshop/budgets/{id_budget}/": _W,
    "POST /api/workshop/budgets/{id_budget}/items/": _W,
    "PATCH /api/workshop/budgets/{id_budget}/items/{id_budget_item}/": _W,
    "DELETE /api/workshop/budgets/{id_budget}/items/{id_budget_item}/": _W,
    "POST /api/workshop/budgets/{id_budget}/send/": _W,
    "PATCH /api/workshop/budgets/{id_budget}/items/{id_budget_item}/execution/": _W,
    "GET /api/workshop/clients/": _W,
    "GET /api/workshop/clients/{id_client}/vehicles/": _W,
    "GET /api/workshop/vehicles/{id_vehicle}/history/": _W,
    # 8.6 chat
    "GET /api/chats/": "account",
    "POST /api/chats/{workshop_id}/open/": "client",
    "GET /api/chats/{id_chat}/": "account",
    "GET /api/chats/{id_chat}/messages/": "account",
    "POST /api/chats/{id_chat}/messages/": "account",
    "POST /api/chats/{id_chat}/read/": "account",
    # 8.7 reviews
    "GET /api/workshops/{workshop_id}/reviews/": "public",
    "POST /api/reviews/": "client",
    "POST /api/denunciations/": "client",
    "GET /api/workshop/reviews/": _W,
    "POST /api/workshop/reviews/{id}/response/": _W,
    # 8.8 promotions
    "GET /api/promotions/": "public",
    "GET /api/workshops/{workshop_id}/promotions/": "public",
    "GET /api/workshop/promotions/": _W,
    "POST /api/workshop/promotions/": _W,
    "PATCH /api/workshop/promotions/{id_promotion}/": _W,
    "GET /api/workshop/promotions/{id_promotion}/advertisements/": _W,
    "POST /api/workshop/promotions/{id_promotion}/advertisements/": _W,
    # 8.9 notifications
    "GET /api/notifications/": "account",
    "GET /api/notifications/unread-count/": "account",
    "POST /api/notifications/{id}/read/": "account",
    "POST /api/notifications/read-all/": "account",
    # 8.10 moderation
    "GET /api/admin/denunciations/": "admin",
    "GET /api/admin/denunciations/{id}/": "admin",
    "PATCH /api/admin/denunciations/{id}/": "admin",
    "POST /api/admin/reviews/{id}/hide/": "admin",
    "GET /api/admin/service-requests/": "admin",
    "POST /api/admin/service-requests/{id}/approve/": "admin",
    "POST /api/admin/service-requests/{id}/reject/": "admin",
    # 8.11 infraestrutura
    "GET /api/health/": "public",
    "GET /api/health/ready/": "public",
    "GET /api/health/jobs/": "public",  # batimento da rotina de expiração (BE-092)
}

# Parâmetro de caminho → entidade do mundo. `{id}` usa o segmento anterior.
ENTITY_BY_PARAM = {
    "id_attendance": "attendance",
    "id_budget": "budget",
    "id_budget_item": "budget_item",
    "id_client": "client",
    "id_vehicle": "vehicle",
    "id_chat": "chat",
    "id_workshop": "workshop",
    "workshop_id": "workshop",
    "id_promotion": "promotion",
    "id_product": "product",
    "id_workshop_service": "workshop_service",
    "record": "history_record",
}
ENTITY_BY_SEGMENT = {
    "budgets": "budget",
    "notifications": "notification",
    "reviews": "review",
    "denunciations": "denunciation",
    "service-requests": "service_request",
    "workshops": "workshop",
}
# Parâmetros que apontam para um alvo público, não para um recurso do dono.
TARGET_PARAMS = {"POST /api/chats/{workshop_id}/open/": {"workshop_id"}}

MODEL_BY_ENTITY = {
    "attendance": Attendance,
    "budget": Budget,
    "budget_item": BudgetItem,
    "client": Client,
    "vehicle": Vehicle,
    "chat": Chat,
    "workshop": Workshop,
    "promotion": Promotion,
    "product": Product,
    "workshop_service": WorkshopService,
    "history_record": RegisterMaintenance,
    "notification": Notification,
    "review": Review,
    "denunciation": Denunciation,
    "service_request": WorkshopService,
}


# ------------------------------------------------------------------ schema


@cache
def openapi():
    return SchemaGenerator().get_schema(request=None, public=True)


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    params: tuple  # (nome, formato)

    @property
    def key(self):
        return f"{self.method} {self.path}"

    def __str__(self):
        return self.key

    def entity_of(self, param):
        if param in ENTITY_BY_PARAM:
            return ENTITY_BY_PARAM[param]
        if param == "id":
            segment = self.path.split("/{id}/")[0].rsplit("/", 1)[-1]
            if segment in ENTITY_BY_SEGMENT:
                return ENTITY_BY_SEGMENT[segment]
        raise AssertionError(
            f"{self.key}: parâmetro de caminho '{param}' sem entidade conhecida. "
            "Use o nome `id_<entidade>` e acrescente-o a ENTITY_BY_PARAM (e a entidade em "
            "`Side.entity`, apps/core/tests/world.py)."
        )

    def owned_params(self):
        targets = TARGET_PARAMS.get(self.key, set())
        return [name for name, _ in self.params if name not in targets]

    def url(self, values):
        url = self.path
        for name, _ in self.params:
            url = url.replace("{" + name + "}", str(values[name]))
        return url

    def dummy_url(self):
        return self.url(
            {name: uuid.uuid4() if fmt == "uuid" else 1 for name, fmt in self.params}
        )

    @property
    def view_class(self):
        callback = resolve(self.dummy_url()).func
        return getattr(callback, "cls", None) or getattr(callback, "view_class", None)

    @property
    def policy(self):
        return policy_of(self.view_class)

    @property
    def allowed(self):
        return ALLOWED[self.policy]


@cache
def operations():
    found = []
    for path, item in openapi()["paths"].items():
        for method, op in item.items():
            if method not in METHODS:
                continue
            params = tuple(
                (p["name"], p.get("schema", {}).get("format"))
                for p in op.get("parameters", [])
                if p["in"] == "path"
            )
            found.append(Operation(method.upper(), path, params))
    return found


def policy_of(view_class):
    perms = set(view_class.permission_classes)
    if perms <= {AllowAny}:
        return "public"
    if perms & {CoreIsAdmin, ModerationIsAdmin}:
        return "admin"
    if IsWorkshopSetupComplete in perms:
        return "workshop_ready"
    if IsWorkshop in perms:
        return "workshop"
    if IsClient in perms:
        return "client"
    if perms & {IsAccountHolder, IsChatParticipant}:
        return "account"
    if IsAuthenticated in perms:
        return "authenticated"
    raise AssertionError(
        f"{view_class.__name__}: permissões sem política conhecida: {perms}"
    )


# ------------------------------------------------------------------ apoio


@pytest.fixture
def world():
    world = build_world()
    # Sistema "no ar": a rotina de expiração acabou de rodar (GET /api/health/jobs/ → 200).
    heartbeat.record_success(heartbeat.EXPIRATION)
    return world


@pytest.fixture
def actors(world, django_user_model):
    staff = django_user_model.objects.create_user(
        "moderador", "mod@exemplo.com", "x" * 12, is_staff=True
    )
    admin = APIClient()
    admin.force_login(staff)
    new_workshop = PagWorkshopFactory().workshop  # sem serviço: cadastro não concluído
    return {
        "visitor": lambda side=None: APIClient(),
        "client": lambda side="A": open_account_session(
            world.side(side).client, "client"
        ),
        "workshop": lambda side="A": open_account_session(
            world.side(side).workshop, "workshop"
        ),
        "workshop_new": lambda side=None: open_account_session(
            new_workshop, "workshop"
        ),
        "admin": lambda side=None: admin,
    }


def call(api, method, url, body=None):
    if method == "GET":
        return api.get(url)
    return api.generic(
        method, url, json.dumps(body or {}), content_type="application/json"
    )


def values_for(op, world, side, role):
    return {
        name: world.side(side).entity(op.entity_of(name), role) for name, _ in op.params
    }


def snapshot(op, world, side, role):
    """Linhas dos recursos de `side` alcançados pela rota (e dos filhos que a ação mexeria)."""
    rows = {}
    for name in op.owned_params():
        entity = op.entity_of(name)
        value = world.side(side).entity(entity, role)
        if entity == "history_record":
            value = int(str(value).split("-")[1])
        model = MODEL_BY_ENTITY[entity]
        rows[(entity, str(value))] = list(model.objects.filter(pk=value).values())
        if entity == "chat":
            rows[("messages", str(value))] = list(
                Message.objects.filter(chat_id=value).order_by("pk").values()
            )
        if entity in ("budget", "attendance"):
            budgets = Budget.objects.filter(
                **({"pk": value} if entity == "budget" else {"attendance_id": value})
            )
            rows[("budget_items", str(value))] = list(
                BudgetItem.objects.filter(budget__in=budgets).order_by("pk").values()
            )
    return rows


def _cases(predicate):
    return [
        pytest.param(op, role, id=f"{op.key} [{role}]")
        for op in operations()
        for role in ROLES
        if predicate(op, role)
    ]


def _owner_cases():
    def owned(op, role):
        return (
            role in ("client", "workshop")
            and op.policy not in ("public", "admin")
            and role in op.allowed
            and bool(op.owned_params())
        )

    return _cases(owned)


# ------------------------------------------------------------------ matriz


def test_matrix_covers_every_operation_of_the_schema():
    keys = {op.key for op in operations()}
    missing = sorted(keys - set(CONTRACT))
    stale = sorted(set(CONTRACT) - keys)
    assert not missing, (
        f"Endpoints fora da matriz da seção 8 (acrescente em CONTRACT): {missing}"
    )
    assert not stale, f"Endpoints da matriz que sumiram do schema: {stale}"
    assert (
        len(keys) == 91
    )  # 84 da seção 8 + 3 de health + 3 rotas das Fases 3–5 + 1 do BE-094 (OSM)


@pytest.mark.parametrize("op", operations(), ids=str)
def test_permission_classes_match_the_contract(op):
    assert op.policy == CONTRACT[op.key], f"{op.key}: view {op.view_class.__name__}"


@pytest.fixture
def principal(django_user_model):
    """Só a conta do perfil pedido (a permissão é decidida antes de buscar o recurso)."""

    def make(role):
        if role == "visitor":
            return APIClient()
        if role == "client":
            return open_account_session(ClientFactory(), "client")
        if role == "workshop":
            return open_account_session(make_ready_workshop(), "workshop")
        if role == "workshop_new":
            return open_account_session(PagWorkshopFactory().workshop, "workshop")
        staff = django_user_model.objects.create_user(
            "moderador", "mod@exemplo.com", "x" * 12, is_staff=True
        )
        api = APIClient()
        api.force_login(staff)
        return api

    return make


@pytest.mark.parametrize(
    ("op", "role"), _cases(lambda op, role: role not in op.allowed)
)
def test_denied_roles(op, role, principal):
    response = call(principal(role), op.method, op.dummy_url())

    if role == "visitor":
        assert response.status_code == 401, response.content
        assert response["WWW-Authenticate"] == "Session"
    else:
        assert response.status_code == 403, response.content
    assert set(response.json()) == {"detail"}, "a recusa não pode carregar dados"


@pytest.mark.parametrize(("op", "role"), _owner_cases())
def test_resource_of_another_owner_is_404_and_untouched(op, role, world, actors):
    foreign = values_for(op, world, "B", role)
    for (
        name,
        _,
    ) in op.params:  # alvos públicos (ex.: oficina do chat) continuam do lado A
        if name not in op.owned_params():
            foreign[name] = world.a.entity(op.entity_of(name), role)
    before = snapshot(op, world, "B", role)

    response = call(actors[role]("A"), op.method, op.url(foreign))

    assert response.status_code == 404, (
        f"{op.key} como {role} A sobre B: {response.status_code} {response.content!r}"
    )
    assert set(response.json()) == {"detail"}
    assert snapshot(op, world, "B", role) == before, "os dados de B mudaram"

    # Controle positivo: os mesmos ids existem e B alcança a rota (o 404 acima é por dono).
    own = call(actors[role]("B"), op.method, op.url(foreign))
    assert own.status_code not in (401, 403, 404), (
        f"controle positivo falhou: {own.status_code} {own.content!r}"
    )


@pytest.mark.parametrize(
    ("op", "role"),
    _cases(
        lambda op, role: op.method == "GET" and role != "admin" and role in op.allowed
    ),
)
def test_reads_never_contain_private_data_of_the_other_side(op, role, world, actors):
    owner = role if role in ("client", "workshop") else None
    side = (
        "B" if op.policy == "public" else "A"
    )  # leitura pública: os dados públicos de B
    response = call(
        actors[role]("A") if owner else actors[role](),
        "GET",
        op.url(values_for(op, world, side, owner)),
    )

    assert response.status_code < 500
    assert world.b.marker.lower() not in response.content.decode().lower(), (
        f"{op.key} vazou dado privado de B"
    )


# ------------------------------------------------------------- mass assignment

# Campos de dono, status e valores calculados nunca são graváveis pelo corpo.
FORBIDDEN_REQUEST_FIELDS = {
    "id_client",
    "id_workshop",
    "password_hash",
    "total_price",
    "advertising_price",
    "payment_status",
    "status",
    "email",
    "cnpj",
}
# Exceções do contrato (seção 8): alvo escolhido pelo usuário ou ação explícita.
REQUEST_FIELD_ALLOWLIST = {
    ("POST /api/attendances/", "id_workshop"),  # oficina escolhida pelo cliente
    ("POST /api/favorites/", "id_workshop"),  # oficina favoritada
    (
        "POST /api/workshop/attendances/{id_attendance}/transition/",
        "status",
    ),  # a própria ação
    (
        "PATCH /api/admin/denunciations/{id}/",
        "status_denunciation",
    ),  # decisão do moderador
    (
        "POST /api/workshop/promotions/",
        "status_promotion",
    ),  # active/inactive pela oficina
    ("PATCH /api/workshop/promotions/{id_promotion}/", "status_promotion"),
    ("POST /api/auth/register/", "email"),
    ("POST /api/auth/register/", "cnpj"),
    ("POST /api/auth/login/", "email"),
    ("POST /api/auth/password-reset/", "email"),
}


def _writable_properties(schema, components):
    if "$ref" in schema:
        return _writable_properties(
            components[schema["$ref"].rsplit("/", 1)[-1]], components
        )
    names = set()
    for key in ("allOf", "oneOf", "anyOf"):
        for part in schema.get(key, []):
            names |= _writable_properties(part, components)
    if schema.get("type") == "array" and "items" in schema:
        names |= _writable_properties(schema["items"], components)
    for name, prop in schema.get("properties", {}).items():
        if not prop.get("readOnly"):
            names.add(name)
    return names


def test_request_bodies_have_no_owner_status_or_computed_fields():
    components = openapi()["components"]["schemas"]
    offenders = []
    for path, item in openapi()["paths"].items():
        for method, op in item.items():
            body = op.get("requestBody") if isinstance(op, dict) else None
            if not body:
                continue
            key = f"{method.upper()} {path}"
            names = set()
            for content in body["content"].values():
                names |= _writable_properties(content["schema"], components)
            for name in sorted(names):
                forbidden = name in FORBIDDEN_REQUEST_FIELDS or name.startswith(
                    "status"
                )
                if forbidden and (key, name) not in REQUEST_FIELD_ALLOWLIST:
                    offenders.append(f"{key}: {name}")
    assert not offenders, (
        "campos de dono/status/calculados aceitos no corpo: " + ", ".join(offenders)
    )


def _vehicle_body(**extra):
    return {
        "brand": "Fiat",
        "model": "Argo",
        "year_fabrication": 2020,
        "year_model": 2021,
        "plate": "QWE1R23",
        "fuel": "flex",
        "exchange": "manual",
        "mileage_km": 1000,
        **extra,
    }


class TestMassAssignmentIsIgnored:
    """Corpo com `id_client`, `id_workshop`, `status*`, `total_price` ou `password_hash`."""

    def test_vehicle_create_and_update_keep_the_owner(self, world, actors):
        api = actors["client"]("A")
        response = api.post(
            "/api/vehicles/",
            _vehicle_body(id_client=world.b.client.pk, client=world.b.client.pk),
        )
        assert response.status_code == 201, response.content
        assert (
            Vehicle.objects.get(pk=response.json()["id"]).client_id == world.a.client.pk
        )

        url = f"/api/vehicles/{world.a.vehicle.pk}/"
        assert (
            api.patch(
                url, {"id_client": world.b.client.pk, "color": "Azul"}
            ).status_code
            == 200
        )
        assert Vehicle.objects.get(pk=world.a.vehicle.pk).client_id == world.a.client.pk

    def test_attendance_is_created_for_the_caller_as_requested(self, world, actors):
        body = {
            "id_workshop": world.a.workshop.pk,
            "id_vehicle": world.a.vehicle.pk,
            "id_client": world.b.client.pk,
            "status_attendance": "approved",
            "status": "approved",
        }
        response = actors["client"]("A").post("/api/attendances/", body, format="json")
        assert response.status_code == 201, response.content
        attendance = Attendance.objects.get(pk=response.json()["id"])
        assert (attendance.client_id, attendance.status_attendance) == (
            world.a.client.pk,
            "requested",
        )

    def test_attendance_with_a_foreign_vehicle_is_refused(self, world, actors):
        body = {"id_workshop": world.a.workshop.pk, "id_vehicle": world.b.vehicle.pk}
        response = actors["client"]("A").post("/api/attendances/", body, format="json")
        assert response.status_code in (400, 404)
        assert not Attendance.objects.filter(
            vehicle=world.b.vehicle, client=world.a.client
        ).exists()

    def test_favorite_belongs_to_the_caller(self, world, actors):
        body = {"id_workshop": world.b.workshop.pk, "id_client": world.b.client.pk}
        assert actors["client"]("A").post(
            "/api/favorites/", body, format="json"
        ).status_code in (200, 201)
        assert Favorite.objects.filter(
            client=world.a.client, workshop=world.b.workshop
        ).exists()
        assert Favorite.objects.filter(client=world.b.client).count() == 1

    def test_account_update_ignores_credentials_and_status(self, world, actors):
        client = world.a.client
        body = {
            "name": "Novo nome",
            "email": "outro@exemplo.com",
            "password_hash": "x",
            "status": "blocked",
        }
        assert (
            actors["client"]("A").patch("/api/me/", body, format="json").status_code
            == 200
        )
        client.refresh_from_db()
        assert (client.name, client.status) == ("Novo nome", "active")
        assert client.email != "outro@exemplo.com" and client.password_hash != "x"

    def test_workshop_update_ignores_cnpj_email_status_and_password(
        self, world, actors
    ):
        workshop = world.a.workshop
        cnpj, email, password_hash = (
            workshop.cnpj,
            workshop.email,
            workshop.password_hash,
        )
        body = {
            "name_fantasy": "Nova Oficina",
            "cnpj": "11222333000181",
            "email": "x@exemplo.com",
            "status": "blocked",
            "password_hash": "x",
        }
        assert (
            actors["workshop"]("A")
            .patch("/api/workshop/me/", body, format="json")
            .status_code
            == 200
        )
        workshop.refresh_from_db()
        assert workshop.name_fantasy == "Nova Oficina"
        assert (
            workshop.cnpj,
            workshop.email,
            workshop.status,
            workshop.password_hash,
        ) == (
            cnpj,
            email,
            "active",
            password_hash,
        )

    def test_budget_item_ignores_owner_total_and_execution(self, world, actors):
        side = world.a
        attendance = AttendanceFactory(
            client=side.client, workshop=side.workshop, vehicle=side.vehicle
        )
        api = actors["workshop"]("A")
        created = api.post(
            f"/api/workshop/attendances/{attendance.pk}/budget/", {}, format="json"
        )
        assert created.status_code == 201, created.content
        new_budget = created.json()["id"]

        body = {
            "item_type": "labor",
            "description": "Mão de obra",
            "quantity": "1",
            "unit_price": "50.00",
            "id_workshop": world.b.workshop.pk,
            "total_price": "1.00",
            "execution_status": "executed",
        }
        response = api.post(
            f"/api/workshop/budgets/{new_budget}/items/", body, format="json"
        )
        assert response.status_code == 201, response.content
        item = BudgetItem.objects.get(pk=response.json()["id"])
        assert (item.workshop_id, item.execution_status) == (
            side.workshop.pk,
            "pending",
        )
        assert str(Budget.objects.get(pk=new_budget).total_price) == "50.00"

        patch = {
            "total_price": "1.00",
            "status_budget": "approved",
            "observations": "Revisado",
        }
        assert (
            api.patch(
                f"/api/workshop/budgets/{new_budget}/", patch, format="json"
            ).status_code
            == 200
        )
        budget = Budget.objects.get(pk=new_budget)
        assert (budget.status_budget, str(budget.total_price)) == ("pending", "50.00")

    def test_workshop_attendance_update_ignores_status_and_client(self, world, actors):
        attendance = world.a.attendance
        body = {
            "status_attendance": "delivered",
            "id_client": world.b.client.pk,
            "mileage_km": 70000,
        }
        url = f"/api/workshop/attendances/{attendance.pk}/"
        assert (
            actors["workshop"]("A").patch(url, body, format="json").status_code == 200
        )
        attendance.refresh_from_db()
        assert (
            attendance.status_attendance,
            attendance.client_id,
            attendance.mileage_km,
        ) == (
            "waiting_approval",
            world.a.client.pk,
            70000,
        )

    def test_advertisement_price_and_status_are_set_by_the_server(self, world, actors):
        promotion = world.a.promotion
        now = timezone.now()
        body = {
            "image": jpeg_upload(),
            "date_start": (now + timedelta(days=1)).isoformat(),
            "date_end": (now + timedelta(days=3)).isoformat(),
            "advertising_price": "0.01",
            "payment_status": "paid",
            "status_advertisement": "active",
        }
        url = f"/api/workshop/promotions/{promotion.pk}/advertisements/"
        response = actors["workshop"]("A").post(url, body, format="multipart")
        assert response.status_code == 201, response.content
        ad = PromotionAdvertisement.objects.get(pk=response.json()["id"])
        assert (ad.payment_status, ad.status_advertisement) == ("pending", "pending")
        assert ad.advertising_price > 1

    def test_custom_service_is_a_pending_request_of_the_caller(self, world, actors):
        body = {
            "name_local": "Polimento técnico",
            "id_suggested_category": world.a.service_request.suggested_category_id,
            "price_base": "90.00",
            "duration_estimate": 30,
            "id_workshop": world.b.workshop.pk,
            "status_solicitation": "approved",
        }
        response = actors["workshop"]("A").post(
            "/api/workshop/services/", body, format="json"
        )
        assert response.status_code == 201, response.content
        service = WorkshopService.objects.get(pk=response.json()["id"])
        assert (service.workshop_id, service.status_solicitation) == (
            world.a.workshop.pk,
            "pending",
        )

    def test_product_belongs_to_the_caller(self, world, actors):
        body = {
            "name": "Óleo 5W30",
            "price": "45.00",
            "id_workshop": world.b.workshop.pk,
        }
        response = actors["workshop"]("A").post(
            "/api/workshop/products/", body, format="multipart"
        )
        assert response.status_code == 201, response.content
        assert (
            Product.objects.get(pk=response.json()["id"]).workshop_id
            == world.a.workshop.pk
        )

    def test_promotion_cannot_be_created_expired_nor_for_another_workshop(
        self, world, actors
    ):
        now = timezone.now()
        body = {
            "title": "Desconto",
            "type_discount": "percentage",
            "discount_value": "10",
            "date_start": now.isoformat(),
            "date_end": (now + timedelta(days=5)).isoformat(),
            "id_workshop_service": world.a.workshop_service.pk,
            "id_workshop": world.b.workshop.pk,
        }
        api = actors["workshop"]("A")
        assert (
            api.post(
                "/api/workshop/promotions/",
                {**body, "status_promotion": "expired"},
                format="multipart",
            ).status_code
            == 400
        )
        response = api.post("/api/workshop/promotions/", body, format="multipart")
        assert response.status_code == 201, response.content
        assert (
            Promotion.objects.get(pk=response.json()["id"]).workshop_id
            == world.a.workshop.pk
        )

    def test_message_sender_and_status_come_from_the_session(self, world, actors):
        chat = world.a.chat
        body = {
            "content": "Olá",
            "sender_workshop": world.b.workshop.pk,
            "status_message": "read",
            "sender": "workshop",
        }
        response = actors["client"]("A").post(
            f"/api/chats/{chat.pk}/messages/", body, format="json"
        )
        assert response.status_code == 201, response.content
        message = Message.objects.get(pk=response.json()["id"])
        assert (
            message.sender_client_id,
            message.sender_workshop_id,
            message.status_message,
        ) == (
            world.a.client.pk,
            None,
            "sent",
        )

    def test_denunciation_starts_pending_for_the_caller(self, world, actors):
        body = {
            "target_type": "promotion",
            "target_id": str(world.b.promotion.pk),
            "reason": "spam",
            "status_denunciation": "upheld",
            "moderation_decision": "x",
            "id_client": world.b.client.pk,
        }
        response = actors["client"]("A").post(
            "/api/denunciations/", body, format="json"
        )
        assert response.status_code == 201, response.content
        denunciation = Denunciation.objects.get(pk=response.json()["id"])
        assert (
            denunciation.client_id,
            denunciation.status_denunciation,
            denunciation.moderation_decision,
        ) == (
            world.a.client.pk,
            "pending",
            None,
        )

    def test_review_of_a_foreign_budget_is_404(self, world, actors):
        body = {"id_budget": world.b.delivered_budget.pk, "rating": 1}
        Review.objects.filter(budget=world.b.delivered_budget).delete()
        response = actors["client"]("A").post("/api/reviews/", body, format="json")
        assert response.status_code == 404
        assert not Review.objects.filter(budget=world.b.delivered_budget).exists()

    def test_review_response_does_not_change_the_review_status(self, world, actors):
        review = world.a.review
        body = {
            "workshop_response": "Obrigado!",
            "status_review": "hidden",
            "rating": 1,
        }
        response = actors["workshop"]("A").post(
            f"/api/workshop/reviews/{review.pk}/response/", body, format="json"
        )
        assert response.status_code == 200, response.content
        review.refresh_from_db()
        assert (review.status_review, review.rating) == ("published", 5)


# ------------------------------------------------------- casos dirigidos


def _align_sequences():
    """Faz o próximo cliente e a próxima oficina nascerem com o mesmo id."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT GREATEST((SELECT last_value FROM client_id_client_seq), "
            "(SELECT last_value FROM workshop_id_workshop_seq)) + 1000"
        )
        (start,) = cursor.fetchone()
        cursor.execute("SELECT setval('client_id_client_seq', %s)", [start])
        cursor.execute("SELECT setval('workshop_id_workshop_seq', %s)", [start])


class TestRoleConfusion:
    """Cliente e oficina com o MESMO id numérico (tabelas e sequências separadas)."""

    @pytest.fixture
    def twins(self):
        _align_sequences()
        client = ClientFactory()
        workshop = PagWorkshopFactory().workshop
        assert client.pk == workshop.pk
        return client, workshop

    def test_notifications_are_scoped_by_role_and_id(self, twins):
        client, workshop = twins
        mine = NotificationFactory(client=None, workshop=workshop, message="da oficina")
        theirs = NotificationFactory(client=client, message="do cliente")
        api = open_account_session(workshop, "workshop")

        listed = {row["id"] for row in api.get("/api/notifications/").json()["results"]}
        assert listed == {mine.pk}
        assert api.get("/api/notifications/unread-count/").json() == {"count": 1}
        assert api.post(f"/api/notifications/{theirs.pk}/read/").status_code == 404
        api.post("/api/notifications/read-all/")
        theirs.refresh_from_db()
        assert theirs.read_status is False

    def test_chats_are_scoped_by_role_and_id(self, twins):
        client, workshop = twins
        foreign = ChatFactory(
            client=client
        )  # conversa do cliente gêmeo com outra oficina
        MessageFactory(chat=foreign, content="privada")
        api = open_account_session(workshop, "workshop")

        assert api.get("/api/chats/").json()["count"] == 0
        assert api.get(f"/api/chats/{foreign.pk}/").status_code == 404
        assert api.get(f"/api/chats/{foreign.pk}/messages/").status_code == 404


def test_opening_a_chat_with_a_foreign_workshop_never_returns_the_other_clients_chat(
    world, actors
):
    response = actors["client"]("A").post(f"/api/chats/{world.b.workshop.pk}/open/")

    assert response.status_code == 201
    chat = Chat.objects.get(pk=response.json()["id"])
    assert (chat.client_id, chat.workshop_id) == (
        world.a.client.pk,
        world.b.workshop.pk,
    )
    assert chat.pk != world.b.chat.pk
    messages = actors["client"]("A").get(f"/api/chats/{chat.pk}/messages/").json()
    assert messages["count"] == 0


def test_workshop_never_reads_history_of_a_vehicle_it_did_not_serve(world, actors):
    """Mesmo com `history_shared=true` no veículo de B (DP-07)."""
    response = actors["workshop"]("A").get(
        f"/api/workshop/vehicles/{world.b.vehicle.pk}/history/"
    )
    assert response.status_code == 404


# ----------------------------------------------------------- Django Admin


class TestDjangoAdmin:
    """O Django Admin (DP-03) só abre para usuário Django `is_staff` com permissão do modelo."""

    @pytest.fixture
    def changelists(self):
        from django.contrib import admin

        urls = []
        for model in admin.site._registry:
            meta = model._meta
            urls.append(f"/admin/{meta.app_label}/{meta.model_name}/")
        assert len(urls) >= 8
        return urls

    def test_visitor_and_account_sessions_are_sent_to_the_login(
        self, changelists, world
    ):
        for api in (
            APIClient(),
            open_account_session(world.a.client, "client"),
            open_account_session(world.a.workshop, "workshop"),
        ):
            for url in ["/admin/", *changelists]:
                response = api.get(url)
                assert response.status_code == 302, url
                assert response["Location"].startswith("/admin/login/"), url

    def test_non_staff_user_is_sent_to_the_login(self, changelists, django_user_model):
        api = APIClient()
        api.force_login(
            django_user_model.objects.create_user(
                "comum", "comum@exemplo.com", "x" * 12
            )
        )
        for url in changelists:
            assert api.get(url).status_code == 302, url

    def test_staff_without_model_permissions_gets_403(
        self, changelists, django_user_model
    ):
        api = APIClient()
        api.force_login(
            django_user_model.objects.create_user(
                "estagiario", "e@exemplo.com", "x" * 12, is_staff=True
            )
        )
        for url in changelists:
            assert api.get(url).status_code == 403, url

    def test_admin_actions_require_csrf(self, django_user_model, world):
        user = django_user_model.objects.create_superuser(
            "chefe", "chefe@exemplo.com", "x" * 12
        )
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(user)
        response = api.post(
            "/admin/accounts/client/",
            {"action": "block_accounts", "_selected_action": [world.a.client.pk]},
        )
        assert response.status_code == 403
        world.a.client.refresh_from_db()
        assert world.a.client.status == "active"
