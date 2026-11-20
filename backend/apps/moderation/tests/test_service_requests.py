"""BE-074: solicitações de serviço personalizado (approve_/reject_workshop_service_request)."""

import threading

import pytest
from apps.catalog.models import Service, ServiceCategory, WorkshopService
from apps.core.exceptions import ApiConflict
from apps.core.tests.factories import (
    ServiceCategoryFactory,
    ServiceFactory,
    WorkshopFactory,
    WorkshopServiceFactory,
    make_ready_workshop,
)
from apps.moderation.services import approve_service_request
from apps.notifications.models import Notification
from django.db import connections

URL = "/api/admin/service-requests/"
pytestmark = pytest.mark.django_db


def custom_request(
    workshop=None, *, name="Cristalização de faróis", category="default", **kwargs
):
    """Serviço personalizado da oficina: nasce `pending` (solicitação de inclusão)."""
    if category == "default":
        category = ServiceCategory.objects.get(name="Estética")
    return WorkshopServiceFactory(
        workshop=workshop or make_ready_workshop(),
        service=None,
        name_local=name,
        description_local=kwargs.pop("description", "Polimento dos faróis amarelados"),
        suggested_category=category,
        status_solicitation="pending",
        **kwargs,
    )


def approve(api, request, payload=None):
    return api.post(f"{URL}{request.pk}/approve/", payload or {}, format="json")


def reject(api, request, payload):
    return api.post(f"{URL}{request.pk}/reject/", payload, format="json")


def global_services_named(name):
    return Service.objects.filter(name__iexact=name)


# ------------------------------------------------------------------ lista


class TestList:
    def test_default_is_the_pending_queue_oldest_first(self, staff_client):
        first = custom_request(name="Cristalização de faróis")
        second = custom_request(name="Higienização de ar-condicionado", category=None)
        decided = custom_request(name="Envelopamento")
        WorkshopService.objects.filter(pk=decided.pk).update(
            status_solicitation="rejected", motivation_rejection="Fora do escopo"
        )
        WorkshopServiceFactory(
            workshop=first.workshop
        )  # serviço do catálogo: não é solicitação

        response = staff_client.get(URL)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["results"]] == [first.pk, second.pk]
        item = body["results"][0]
        estetica = ServiceCategory.objects.get(name="Estética")
        assert item["workshop"] == {
            "id": first.workshop_id,
            "name_fantasy": first.workshop.name_fantasy,
        }
        assert (item["name_local"], item["description_local"]) == (
            "Cristalização de faróis",
            "Polimento dos faróis amarelados",
        )
        assert (item["id_suggested_category"], item["suggested_category_name"]) == (
            estetica.pk,
            "Estética",
        )
        assert (
            item["status_solicitation"],
            item["id_service"],
            item["service_name"],
        ) == ("pending", None, None)
        assert body["results"][1]["suggested_category_name"] is None
        assert "cnpj" not in str(body) and "email" not in str(body)

    def test_status_filter_includes_decided(self, staff_client):
        pending = custom_request(name="A")
        rejected = custom_request(name="B")
        WorkshopService.objects.filter(pk=rejected.pk).update(
            status_solicitation="rejected", motivation_rejection="x"
        )

        ids = [
            i["id"]
            for i in staff_client.get(URL, {"status": "pending,rejected"}).json()[
                "results"
            ]
        ]
        only_rejected = staff_client.get(URL, {"status": "rejected"}).json()["results"]

        assert ids == [pending.pk, rejected.pk]
        assert [(i["id"], i["motivation_rejection"]) for i in only_rejected] == [
            (rejected.pk, "x")
        ]

    def test_invalid_status_is_400(self, staff_client):
        assert staff_client.get(URL, {"status": "pending,closed"}).status_code == 400

    def test_access_matrix(self, api_client, client_session, ready_workshop_session):
        assert api_client.get(URL).status_code == 401
        assert client_session.get(URL).status_code == 403
        assert ready_workshop_session.get(URL).status_code == 403


# ---------------------------------------------------------------- aprovar


class TestApprove:
    def test_new_name_creates_global_service_and_notifies(self, staff_client, commit):
        request = custom_request()
        before = Service.objects.count()

        response = commit(approve, staff_client, request)

        assert response.status_code == 200, response.json()
        body = response.json()
        created = Service.objects.get(name="Cristalização de faróis")
        assert Service.objects.count() == before + 1
        assert (created.category.name, created.description) == (
            "Estética",
            "Polimento dos faróis amarelados",
        )
        assert (
            body["status_solicitation"],
            body["id_service"],
            body["service_name"],
        ) == (
            "approved",
            created.pk,
            "Cristalização de faróis",
        )
        assert body["date_solicitation_response"] is not None
        [(title, message, url)] = Notification.objects.filter(
            workshop=request.workshop
        ).values_list("title", "message", "url")
        assert (title, url) == ("Serviço aprovado", "w-services.html")
        assert "Cristalização de faróis" in message
        assert staff_client.get("/api/services/?q=cristalizacao").json()["count"] == 1

    def test_existing_name_is_reused_without_duplicating(self, staff_client):
        existing = Service.objects.get(name="Troca de óleo")
        request = custom_request(
            name="TROCA DE ÓLEO", category=ServiceCategoryFactory()
        )
        before = Service.objects.count()

        response = approve(
            staff_client, request, {"description": "não deve sobrescrever"}
        )

        assert response.status_code == 200
        assert Service.objects.count() == before
        assert response.json()["id_service"] == existing.pk
        existing.refresh_from_db()
        assert existing.description == "Serviço de troca de óleo do motor"
        assert existing.category.name == "Manutenção"
        request.refresh_from_db()
        assert request.name_local == "TROCA DE ÓLEO"  # a oficina mantém o nome dela

    def test_overrides_name_description_and_category(self, staff_client):
        request = custom_request(name="cristalizacao farol")
        motor = ServiceCategory.objects.get(name="Motor")

        response = approve(
            staff_client,
            request,
            {
                "name": "  Cristalização   de faróis ",
                "description": "Descrição do catálogo",
                "id_category": motor.pk,
            },
        )

        assert response.status_code == 200
        created = Service.objects.get(pk=response.json()["id_service"])
        assert (created.name, created.description, created.category_id) == (
            "Cristalização de faróis",
            "Descrição do catálogo",
            motor.pk,
        )
        assert response.json()["name_local"] == "cristalizacao farol"

    def test_new_service_without_category_is_400(self, staff_client):
        request = custom_request(category=None)

        response = approve(staff_client, request)

        assert response.status_code == 400
        assert response.json() == {
            "id_category": ["Informe a categoria do novo serviço global."]
        }
        request.refresh_from_db()
        assert request.status_solicitation == "pending"
        assert not global_services_named("Cristalização de faróis").exists()

    def test_without_category_but_existing_name_is_reused(self, staff_client):
        request = custom_request(name="Troca de óleo", category=None)
        assert approve(staff_client, request).status_code == 200

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"id_category": 999999}, "id_category"),
            ({"id_category": 0}, "id_category"),
            ({"name": "x" * 256}, "name"),
        ],
    )
    def test_invalid_body_is_400(self, staff_client, payload, field):
        response = approve(staff_client, custom_request(), payload)
        assert response.status_code == 400
        assert field in response.json()

    def test_already_decided_is_409(self, staff_client):
        request = custom_request()
        assert approve(staff_client, request).status_code == 200

        response = approve(staff_client, request)
        assert response.status_code == 409
        assert response.json() == {"detail": "Esta solicitação já foi aprovada."}
        response = reject(staff_client, request, {"motivation": "tarde demais"})
        assert response.status_code == 409

    def test_workshop_already_has_the_global_service_is_409(self, staff_client):
        workshop = make_ready_workshop()
        existing = ServiceFactory(name="Cristalização de faróis")
        WorkshopServiceFactory(workshop=workshop, service=existing)
        request = custom_request(workshop, name="cristalização de faróis")

        response = approve(staff_client, request)

        assert response.status_code == 409
        assert "já possui o serviço global" in response.json()["detail"]
        request.refresh_from_db()
        assert request.status_solicitation == "pending"

    def test_catalog_service_or_unknown_id_is_404(self, staff_client):
        catalog_item = WorkshopServiceFactory()
        assert (
            staff_client.post(
                f"{URL}{catalog_item.pk}/approve/", {}, format="json"
            ).status_code
            == 404
        )
        assert (
            staff_client.post(f"{URL}999999/approve/", {}, format="json").status_code
            == 404
        )
        assert (
            staff_client.post(
                f"{URL}{catalog_item.pk}/reject/", {"motivation": "x"}, format="json"
            ).status_code
            == 404
        )

    def test_access_matrix(self, api_client, client_session, ready_workshop_session):
        request = custom_request()
        assert approve(api_client, request).status_code == 401
        assert approve(client_session, request).status_code == 403
        assert approve(ready_workshop_session, request).status_code == 403
        request.refresh_from_db()
        assert request.status_solicitation == "pending"


# ---------------------------------------------------------------- rejeitar


class TestReject:
    @pytest.mark.parametrize(
        "payload",
        [{}, {"motivation": ""}, {"motivation": "   "}, {"motivation": "x" * 1001}],
    )
    def test_without_motivation_is_400(self, staff_client, payload):
        request = custom_request()

        response = reject(staff_client, request, payload)

        assert response.status_code == 400
        assert "motivation" in response.json()
        request.refresh_from_db()
        assert request.status_solicitation == "pending"

    def test_rejects_keeps_service_in_the_workshop_and_notifies(
        self, staff_client, commit
    ):
        request = custom_request()

        response = commit(
            reject, staff_client, request, {"motivation": "Já existe como “Polimento”."}
        )

        assert response.status_code == 200
        body = response.json()
        assert (
            body["status_solicitation"],
            body["motivation_rejection"],
            body["id_service"],
        ) == (
            "rejected",
            "Já existe como “Polimento”.",
            None,
        )
        assert WorkshopService.objects.filter(pk=request.pk).exists()
        assert not global_services_named("Cristalização de faróis").exists()
        [(title, message)] = Notification.objects.filter(
            workshop=request.workshop
        ).values_list("title", "message")
        assert title == "Serviço não aprovado"
        assert "Motivo: Já existe como “Polimento”." in message

    def test_already_rejected_is_409(self, staff_client):
        request = custom_request()
        assert reject(staff_client, request, {"motivation": "Não"}).status_code == 200

        response = reject(staff_client, request, {"motivation": "Não"})
        assert response.status_code == 409
        assert response.json() == {"detail": "Esta solicitação já foi rejeitada."}
        assert approve(staff_client, request).status_code == 409


# ------------------------------------------------------------- concorrência


def _run_concurrently(*calls):
    barrier = threading.Barrier(len(calls))
    results, errors = [], []

    def worker(call):
        try:
            barrier.wait()
            results.append(call())
        except Exception as exc:  # noqa: BLE001 — o teste inspeciona as exceções
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results, errors


@pytest.mark.django_db(transaction=True)
def test_concurrent_approvals_of_the_same_new_name_create_one_global_service():
    category = ServiceCategoryFactory()
    first = custom_request(
        WorkshopFactory(), name="Revitalização de plásticos", category=category
    )
    second = custom_request(
        WorkshopFactory(), name="revitalização de plásticos", category=category
    )

    results, errors = _run_concurrently(
        lambda: approve_service_request(first.pk),
        lambda: approve_service_request(second.pk),
    )

    assert not errors and len(results) == 2
    [service] = global_services_named("Revitalização de plásticos")
    assert {ws.service_id for ws in results} == {service.pk}
    assert set(
        WorkshopService.objects.filter(pk__in=[first.pk, second.pk]).values_list(
            "status_solicitation", flat=True
        )
    ) == {"approved"}


@pytest.mark.django_db(transaction=True)
def test_concurrent_approvals_of_the_same_request_succeed_once():
    request = custom_request(
        WorkshopFactory(),
        name="Vitrificação de pintura",
        category=ServiceCategoryFactory(),
    )

    results, errors = _run_concurrently(
        lambda: approve_service_request(request.pk),
        lambda: approve_service_request(request.pk),
    )

    assert len(results) == 1
    assert len(errors) == 1 and isinstance(errors[0], ApiConflict)
    assert global_services_named("Vitrificação de pintura").count() == 1
