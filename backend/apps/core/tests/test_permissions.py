"""BE-028 (setup_complete) e BE-030 (permissões por perfil e por objeto)."""

import pytest
from apps.accounts.principal import Principal
from apps.catalog.models import SolicitationStatus
from apps.core.permissions import (
    WORKSHOP_WIZARD_ROUTES,
    IsAccountHolder,
    IsAdmin,
    IsChatParticipant,
    IsClient,
    IsWorkshop,
    IsWorkshopSetupComplete,
)
from apps.core.tests.factories import (
    ChatFactory,
    ClientFactory,
    MessageFactory,
    OperationHourFactory,
    PagWorkshopFactory,
    ProductFactory,
    RegisterMaintenanceFactory,
    ServiceCategoryFactory,
    VehicleFactory,
    WorkshopFactory,
    WorkshopServiceFactory,
)
from apps.workshops.domain import is_setup_complete
from django.contrib.auth.models import AnonymousUser
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIRequestFactory

PROBES = "apps.core.tests.probe_urls"


def _request(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(
        "moderador", "mod@exemplo.com", "x" * 12, is_staff=True
    )


@pytest.fixture
def plain_user(django_user_model):
    return django_user_model.objects.create_user("comum", "comum@exemplo.com", "x" * 12)


# ------------------------------------------------------------ regra BE-028


@pytest.mark.django_db
class TestSetupCompleteRule:
    def test_new_workshop_is_not_complete(self):
        assert is_setup_complete(WorkshopFactory()) is False

    def test_one_catalog_service_completes_setup(self):
        workshop = WorkshopFactory()
        WorkshopServiceFactory(workshop=workshop)
        assert is_setup_complete(workshop) is True

    def test_hours_and_map_point_are_not_required(self):
        workshop = WorkshopFactory()
        WorkshopServiceFactory(workshop=workshop)
        assert not workshop.operation_hours.exists()
        assert workshop.point_of_interest_id is None
        assert is_setup_complete(workshop) is True

    def test_hours_without_services_do_not_complete_setup(self):
        workshop = WorkshopFactory()
        OperationHourFactory(workshop=workshop)
        assert is_setup_complete(workshop) is False

    def test_pending_custom_service_counts(self):
        workshop = WorkshopFactory()
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Polimento artesanal",
            suggested_category=ServiceCategoryFactory(),
            status_solicitation=SolicitationStatus.PENDING,
        )
        assert is_setup_complete(workshop) is True

    def test_rejected_custom_service_does_not_count(self):
        workshop = WorkshopFactory()
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Serviço recusado",
            suggested_category=ServiceCategoryFactory(),
            status_solicitation=SolicitationStatus.REJECTED,
            motivation_rejection="Duplicado",
        )
        assert is_setup_complete(workshop) is False


# ------------------------------------------------- permissões (unidade)


@pytest.mark.django_db
class TestRolePermissions:
    @pytest.fixture
    def users(self, staff_user, plain_user):
        return {
            "anonymous": AnonymousUser(),
            "client": Principal(ClientFactory(), "client"),
            "workshop": Principal(WorkshopFactory(), "workshop"),
            "admin": staff_user,
            "django_user": plain_user,
        }

    @pytest.mark.parametrize(
        ("permission", "allowed"),
        [
            (IsClient, {"client"}),
            (IsWorkshop, {"workshop"}),
            (IsAccountHolder, {"client", "workshop"}),
            (IsAdmin, {"admin"}),
        ],
    )
    def test_matrix(self, users, permission, allowed):
        for name, user in users.items():
            result = permission().has_permission(_request(user), None)
            assert result is (name in allowed), f"{permission.__name__} × {name}"

    def test_inactive_staff_is_not_admin(self, staff_user):
        staff_user.is_active = False
        assert IsAdmin().has_permission(_request(staff_user), None) is False

    def test_permissions_have_portuguese_messages(self):
        for permission in (
            IsClient,
            IsWorkshop,
            IsAccountHolder,
            IsAdmin,
            IsChatParticipant,
            IsWorkshopSetupComplete,
        ):
            assert permission.message and "permission" not in permission.message.lower()


@pytest.mark.django_db
class TestChatParticipant:
    def test_only_the_two_participants_reach_the_chat(self, staff_user):
        chat = ChatFactory()
        message = MessageFactory(chat=chat)
        permission = IsChatParticipant()
        cases = [
            (Principal(chat.client, "client"), True),
            (Principal(chat.workshop, "workshop"), True),
            (Principal(ClientFactory(), "client"), False),
            (Principal(WorkshopFactory(), "workshop"), False),
            (staff_user, False),
        ]
        for user, expected in cases:
            request = _request(user)
            assert permission.has_object_permission(request, None, chat) is expected
            # Objetos filhos (mensagem) resolvem o chat pelo atributo `chat`.
            assert permission.has_object_permission(request, None, message) is expected

    def test_visitor_and_admin_fail_has_permission(self, staff_user):
        assert (
            IsChatParticipant().has_permission(_request(AnonymousUser()), None) is False
        )
        assert IsChatParticipant().has_permission(_request(staff_user), None) is False


@pytest.mark.django_db
def test_setup_permission_only_decides_for_workshops():
    permission = IsWorkshopSetupComplete()
    new_workshop = Principal(WorkshopFactory(), "workshop")
    ready = WorkshopFactory()
    WorkshopServiceFactory(workshop=ready)

    assert permission.has_permission(_request(new_workshop), None) is False
    assert (
        permission.has_permission(_request(Principal(ready, "workshop")), None) is True
    )
    assert (
        permission.has_permission(_request(Principal(ClientFactory(), "client")), None)
        is True
    )


# --------------------------------------------- permissões (API, sondas)


@pytest.mark.django_db
class TestWorkshopSetupBlocking:
    """BE-028: rotas administrativas da oficina bloqueadas até o cadastro oficial
    (rota real de BE-049; antes da Fase 3 era uma sonda)."""

    URL = "/api/workshop/attendances/"

    def test_new_workshop_gets_403_with_detail(self, account_session):
        workshop = PagWorkshopFactory().workshop
        response = account_session(workshop, "workshop").get(self.URL)
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Conclua o cadastro da oficina para acessar este recurso."
        }

    def test_access_is_released_after_first_service(self, account_session):
        workshop = PagWorkshopFactory().workshop
        api = account_session(workshop, "workshop")
        assert api.get(self.URL).status_code == 403

        WorkshopServiceFactory(workshop=workshop)

        assert api.get(self.URL).status_code == 200
        me = api.get("/api/auth/me/").json()["user"]
        assert me["setup_complete"] is True

    def test_wizard_route_is_open_before_setup(self, account_session):
        workshop = PagWorkshopFactory().workshop
        response = account_session(workshop, "workshop").get("/api/workshop/services/")
        assert response.status_code == 200

    def test_client_gets_403_and_visitor_401(self, client_session, api_client):
        assert client_session.get(self.URL).status_code == 403
        response = api_client.get(self.URL)
        assert response.status_code == 401
        assert response["WWW-Authenticate"] == "Session"


def _walk(patterns, prefix=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _walk(entry.url_patterns, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.callback


def test_every_workshop_route_requires_workshop_and_setup_except_wizard():
    """Toda rota `/api/workshop/*` exige IsWorkshop e, fora do assistente T17, IsWorkshopSetupComplete."""
    routes = [
        (route, callback)
        for route, callback in _walk(get_resolver().url_patterns)
        if route.startswith("api/workshop/")
    ]
    assert routes, "nenhuma rota /api/workshop/ encontrada"

    for route, callback in routes:
        view_class = getattr(callback, "cls", None) or getattr(
            callback, "view_class", None
        )
        permissions = list(getattr(view_class, "permission_classes", []))
        segment = route.removeprefix("api/workshop/").split("/", 1)[0]
        assert IsWorkshop in permissions, route
        if segment not in WORKSHOP_WIZARD_ROUTES:
            assert IsWorkshopSetupComplete in permissions, route


# ------------------------------------------------- dono do recurso (mixins)


@pytest.mark.django_db
@pytest.mark.urls(PROBES)
class TestOwnership:
    """BE-030: outro dono → 404; perfil errado → 403; visitante → 401."""

    def test_client_reads_own_vehicle_and_gets_404_for_another(self, account_session):
        mine = VehicleFactory()
        other = VehicleFactory()
        api = account_session(mine.client, "client")

        assert api.get(f"/api/_probe/vehicles/{mine.pk}/").status_code == 200
        assert api.get(f"/api/_probe/vehicles/{other.pk}/").status_code == 404

    def test_list_contains_only_own_vehicles(self, account_session):
        mine = VehicleFactory()
        VehicleFactory(client=mine.client)
        VehicleFactory()  # de outro cliente
        response = account_session(mine.client, "client").get("/api/_probe/vehicles/")

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 2
        assert {row["id_vehicle"] for row in body["results"]} <= set(
            mine.client.vehicles.values_list("pk", flat=True)
        )

    def test_nested_owner_lookup(self, account_session):
        mine = RegisterMaintenanceFactory()
        RegisterMaintenanceFactory()  # histórico de outro cliente
        response = account_session(mine.vehicle.client, "client").get(
            "/api/_probe/maintenance/"
        )
        assert [
            row["id_register_maintenance"] for row in response.json()["results"]
        ] == [mine.pk]

    def test_workshop_calling_client_route_gets_403(self, workshop_session):
        assert workshop_session.get("/api/_probe/vehicles/").status_code == 403

    def test_visitor_gets_401(self, api_client):
        assert api_client.get("/api/_probe/vehicles/").status_code == 401

    def test_workshop_owner_lookup(self, account_session):
        mine = ProductFactory()
        WorkshopServiceFactory(workshop=mine.workshop)
        other = ProductFactory()
        WorkshopServiceFactory(workshop=other.workshop)
        api = account_session(mine.workshop, "workshop")

        assert api.get(f"/api/_probe/workshop/products/{mine.pk}/").status_code == 200
        assert api.get(f"/api/_probe/workshop/products/{other.pk}/").status_code == 404

    def test_chat_participant_object_permission(self, account_session):
        chat = ChatFactory()
        outsider = ClientFactory()

        assert (
            account_session(chat.client, "client")
            .get(f"/api/_probe/chats/{chat.pk}/")
            .status_code
            == 200
        )
        assert (
            account_session(chat.workshop, "workshop")
            .get(f"/api/_probe/chats/{chat.pk}/")
            .status_code
            == 200
        )
        assert (
            account_session(outsider, "client")
            .get(f"/api/_probe/chats/{chat.pk}/")
            .status_code
            == 403
        )
