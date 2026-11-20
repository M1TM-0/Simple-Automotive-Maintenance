"""BE-036 (catálogo global), BE-041 (serviços da oficina) e BE-042 (produtos)."""

import pytest
from apps.catalog.models import Product, Service, SolicitationStatus, WorkshopService
from apps.core.tests.factories import (
    PagWorkshopFactory,
    ProductFactory,
    ServiceCategoryFactory,
    ServiceFactory,
    WorkshopServiceFactory,
    fake_image_upload,
    jpeg_upload,
    make_ready_workshop,
    stored_name,
)
from apps.workshops.domain import is_setup_complete
from django.core.files.storage import default_storage

# ------------------------------------------------------------------ BE-036


@pytest.mark.django_db
class TestGlobalCatalog:
    def test_categories_are_public_and_seeded(self, api_client):
        response = api_client.get("/api/service-categories/")

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 11
        assert set(body["results"][0]) == {"id", "name", "description"}
        assert "max-age=300" in response["Cache-Control"]

    def test_services_contract_fields(self, api_client):
        body = api_client.get("/api/services/", {"page_size": 100}).json()

        assert body["count"] == 62
        item = next(row for row in body["results"] if row["name"] == "Troca de óleo")
        assert set(item) == {
            "id",
            "name",
            "description",
            "id_service_category",
            "category_name",
        }
        assert item["category_name"] == "Manutenção"

    def test_search_ignores_case_and_accents(self, api_client):
        expected = ["Troca de óleo", "Troca de óleo do câmbio"]
        for term in ("oleo", "ÓLEO", "  Óleo  "):
            names = [
                row["name"]
                for row in api_client.get("/api/services/", {"q": term}).json()[
                    "results"
                ]
            ]
            assert names == expected, term

    def test_inactive_service_is_hidden(self, api_client):
        ServiceFactory(name="Serviço desativado xyz", active=False)
        assert (
            api_client.get("/api/services/", {"q": "desativado xyz"}).json()["count"]
            == 0
        )

    def test_filter_by_category(self, api_client):
        category = ServiceCategoryFactory()
        ServiceFactory(name="Serviço A", category=category)
        ServiceFactory(name="Serviço B", category=category)

        body = api_client.get("/api/services/", {"category": category.pk}).json()

        assert [row["name"] for row in body["results"]] == ["Serviço A", "Serviço B"]

    def test_invalid_category_is_400(self, api_client):
        response = api_client.get("/api/services/", {"category": "abc"})
        assert response.status_code == 400
        assert "category" in response.json()

    def test_paginated_with_relative_links(self, api_client):
        body = api_client.get("/api/services/").json()
        assert len(body["results"]) == 20
        assert body["next"] == "/api/services/?page=2"

    def test_stale_session_cookie_does_not_block_public_read(self, api_client):
        api_client.cookies["sessionid"] = "invalida"
        assert api_client.get("/api/services/").status_code == 200


# ------------------------------------------------------------------ BE-041


@pytest.fixture
def new_workshop_session(account_session):
    workshop = PagWorkshopFactory().workshop
    return workshop, account_session(workshop, "workshop")


@pytest.mark.django_db
class TestWorkshopServicesCreate:
    URL = "/api/workshop/services/"

    def test_add_global_service_completes_setup(self, new_workshop_session):
        workshop, api = new_workshop_session
        service = Service.objects.get(name="Troca de óleo")

        response = api.post(
            self.URL,
            {"id_service": service.pk, "price_base": "120.00", "duration_estimate": 45},
            format="json",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["id_service"] == service.pk
        assert body["name"] == "Troca de óleo"
        assert body["category_name"] == "Manutenção"
        assert body["id_service_category"] == service.category_id
        assert body["status_solicitation"] is None
        assert body["price_base"] == "120.00"
        assert is_setup_complete(workshop) is True

    def test_custom_service_is_cleaned_and_pending(self, new_workshop_session):
        _, api = new_workshop_session
        category = ServiceCategoryFactory()

        response = api.post(
            self.URL,
            {
                "name_local": "  Troca   de óleo  especial ",
                "description_local": "Com óleo sintético",
                "id_suggested_category": category.pk,
                "price_base": "150",
                "duration_estimate": 60,
                "status_solicitation": "approved",
                "id_workshop": 999,
            },
            format="json",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["name_local"] == "Troca de óleo especial"
        assert body["name"] == "Troca de óleo especial"
        assert body["status_solicitation"] == SolicitationStatus.PENDING
        assert body["category_name"] == category.name
        assert body["id_service"] is None

    def test_same_global_service_twice_is_409(self, new_workshop_session):
        _, api = new_workshop_session
        payload = {
            "id_service": Service.objects.first().pk,
            "price_base": "10",
            "duration_estimate": 10,
        }
        assert api.post(self.URL, payload, format="json").status_code == 201

        response = api.post(self.URL, payload, format="json")

        assert response.status_code == 409
        assert response.json() == {
            "id_service": ["Este serviço já foi adicionado à oficina."]
        }

    def test_same_custom_name_normalized_is_409(self, new_workshop_session):
        _, api = new_workshop_session
        category = ServiceCategoryFactory()
        base = {
            "id_suggested_category": category.pk,
            "price_base": "10",
            "duration_estimate": 10,
        }
        assert (
            api.post(
                self.URL, {**base, "name_local": "Polimento Artesanal"}, format="json"
            ).status_code
            == 201
        )

        response = api.post(
            self.URL, {**base, "name_local": " polimento   artesanal"}, format="json"
        )

        assert response.status_code == 409
        assert "name_local" in response.json()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("price_base", "-1"),
            ("duration_estimate", 0),
            ("price_base", "1.234"),
            ("price_base", "abc"),
        ],
    )
    def test_invalid_numbers_are_400_by_field(self, new_workshop_session, field, value):
        _, api = new_workshop_session
        payload = {
            "id_service": Service.objects.first().pk,
            "price_base": "10",
            "duration_estimate": 10,
        }
        payload[field] = value

        response = api.post(self.URL, payload, format="json")

        assert response.status_code == 400
        assert field in response.json()

    def test_global_and_custom_together_is_400(self, new_workshop_session):
        _, api = new_workshop_session
        response = api.post(
            self.URL,
            {
                "id_service": Service.objects.first().pk,
                "name_local": "Outro",
                "price_base": "10",
                "duration_estimate": 10,
            },
            format="json",
        )
        assert response.status_code == 400
        assert "id_service" in response.json()

    def test_inactive_global_service_is_400(self, new_workshop_session):
        _, api = new_workshop_session
        inactive = ServiceFactory(active=False)
        response = api.post(
            self.URL,
            {"id_service": inactive.pk, "price_base": "10", "duration_estimate": 10},
            format="json",
        )
        assert response.status_code == 400
        assert "id_service" in response.json()

    def test_custom_without_name_or_category_is_400(self, new_workshop_session):
        _, api = new_workshop_session
        base = {"price_base": "10", "duration_estimate": 10}
        assert (
            "name_local"
            in api.post(self.URL, {**base, "name_local": "   "}, format="json").json()
        )
        no_category = api.post(self.URL, {**base, "name_local": "Algo"}, format="json")
        assert no_category.status_code == 400
        assert "id_suggested_category" in no_category.json()

    def test_rejected_request_shows_motivation_and_stays_listed(
        self, new_workshop_session
    ):
        workshop, api = new_workshop_session
        WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Serviço exótico",
            suggested_category=ServiceCategoryFactory(),
            status_solicitation=SolicitationStatus.REJECTED,
            motivation_rejection="Já existe no catálogo.",
        )

        rows = api.get(self.URL).json()["results"]

        assert rows[0]["status_solicitation"] == "rejected"
        assert rows[0]["motivation_rejection"] == "Já existe no catálogo."
        assert rows[0]["disponibility"] is True

    def test_list_shows_only_own_services(self, new_workshop_session):
        workshop, api = new_workshop_session
        mine = WorkshopServiceFactory(workshop=workshop)
        WorkshopServiceFactory()

        rows = api.get(self.URL).json()["results"]

        assert [row["id"] for row in rows] == [mine.pk]

    def test_access_matrix(self, api_client, client_session):
        assert api_client.get(self.URL).status_code == 401
        assert client_session.get(self.URL).status_code == 403


@pytest.mark.django_db
class TestWorkshopServicesUpdate:
    def test_patch_editable_fields_and_ignore_identity(self, new_workshop_session):
        workshop, api = new_workshop_session
        item = WorkshopServiceFactory(workshop=workshop)
        original_service = item.service_id

        response = api.patch(
            f"/api/workshop/services/{item.pk}/",
            {
                "price_base": "99.90",
                "duration_estimate": 30,
                "disponibility": False,
                "description_local": "Inclui filtro",
                "id_service": Service.objects.exclude(pk=original_service).first().pk,
                "name_local": "Hack",
                "status_solicitation": "approved",
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        item.refresh_from_db()
        assert (str(item.price_base), item.duration_estimate, item.disponibility) == (
            "99.90",
            30,
            False,
        )
        assert item.service_id == original_service
        assert item.name_local is None
        assert item.status_solicitation is None
        assert response.json()["description"] == "Inclui filtro"

    def test_invalid_values_are_400(self, new_workshop_session):
        workshop, api = new_workshop_session
        item = WorkshopServiceFactory(workshop=workshop)
        response = api.patch(
            f"/api/workshop/services/{item.pk}/",
            {"duration_estimate": 0},
            format="json",
        )
        assert response.status_code == 400
        assert "duration_estimate" in response.json()

    def test_other_workshop_service_is_404(self, new_workshop_session):
        _, api = new_workshop_session
        other = WorkshopServiceFactory()
        assert (
            api.patch(
                f"/api/workshop/services/{other.pk}/",
                {"price_base": "1"},
                format="json",
            ).status_code
            == 404
        )

    def test_delete_and_put_are_405(self, new_workshop_session):
        workshop, api = new_workshop_session
        item = WorkshopServiceFactory(workshop=workshop)
        assert api.delete(f"/api/workshop/services/{item.pk}/").status_code == 405
        assert (
            api.put(f"/api/workshop/services/{item.pk}/", {}, format="json").status_code
            == 405
        )
        assert WorkshopService.objects.filter(pk=item.pk).exists()


# ------------------------------------------------------------------ BE-042


@pytest.mark.django_db
class TestWorkshopProducts:
    URL = "/api/workshop/products/"

    def test_create_multipart_with_photo_and_booleans(self, ready_workshop_session):
        response = ready_workshop_session.post(
            self.URL,
            {
                "name": "Filtro de óleo",
                "description": "",
                "category": "Filtros",
                "brand": "Tecfil",
                "price": "35.5",
                "disponibility": "false",
                "photo": jpeg_upload(),
            },
            format="multipart",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["price"] == "35.50"
        assert body["disponibility"] is False
        assert body["active"] is True  # ausente no multipart = padrão true
        assert body["description"] is None
        assert body["photo"].startswith("http://testserver/media/products/")
        assert default_storage.exists(stored_name(body["photo"]))

    def test_negative_price_is_400(self, ready_workshop_session):
        response = ready_workshop_session.post(
            self.URL, {"name": "X", "price": "-5"}, format="multipart"
        )
        assert response.status_code == 400
        assert "price" in response.json()

    def test_name_is_required(self, ready_workshop_session):
        response = ready_workshop_session.post(
            self.URL, {"price": "5"}, format="multipart"
        )
        assert response.status_code == 400
        assert "name" in response.json()

    def test_non_image_photo_is_400(self, ready_workshop_session):
        response = ready_workshop_session.post(
            self.URL,
            {"name": "X", "price": "5", "photo": fake_image_upload()},
            format="multipart",
        )
        assert response.status_code == 400
        assert "photo" in response.json()
        assert not Product.objects.exists()

    def test_deactivated_product_stays_in_workshop_list(
        self, ready_workshop_session, ready_workshop
    ):
        product = ProductFactory(workshop=ready_workshop)

        response = ready_workshop_session.patch(
            f"{self.URL}{product.pk}/", {"active": "false"}, format="multipart"
        )

        assert response.status_code == 200
        assert response.json()["active"] is False
        rows = ready_workshop_session.get(self.URL).json()["results"]
        assert [(row["id"], row["active"]) for row in rows] == [(product.pk, False)]

    def test_patch_replaces_and_removes_photo(
        self, ready_workshop_session, ready_workshop, django_capture_on_commit_callbacks
    ):
        product = ProductFactory(workshop=ready_workshop)
        url = f"{self.URL}{product.pk}/"
        with django_capture_on_commit_callbacks(execute=True):
            first = ready_workshop_session.patch(
                url, {"photo": jpeg_upload()}, format="multipart"
            ).json()["photo"]
        old = stored_name(first)
        assert default_storage.exists(old)

        with django_capture_on_commit_callbacks(execute=True):
            response = ready_workshop_session.patch(
                url, {"photo": ""}, format="multipart"
            )

        assert response.status_code == 200
        assert response.json()["photo"] is None
        assert not default_storage.exists(old)

    def test_partial_patch_keeps_other_fields(
        self, ready_workshop_session, ready_workshop
    ):
        product = ProductFactory(workshop=ready_workshop, disponibility=False)
        ready_workshop_session.patch(
            f"{self.URL}{product.pk}/", {"price": "12.00"}, format="multipart"
        )
        product.refresh_from_db()
        assert (str(product.price), product.disponibility, product.active) == (
            "12.00",
            False,
            True,
        )

    def test_delete_is_405(self, ready_workshop_session, ready_workshop):
        product = ProductFactory(workshop=ready_workshop)
        assert (
            ready_workshop_session.delete(f"{self.URL}{product.pk}/").status_code == 405
        )

    def test_other_workshop_product_is_404(self, ready_workshop_session):
        other = ProductFactory(workshop=make_ready_workshop())
        response = ready_workshop_session.patch(
            f"{self.URL}{other.pk}/", {"price": "1"}, format="multipart"
        )
        assert response.status_code == 404

    def test_access_matrix(self, api_client, client_session, workshop_session):
        assert api_client.get(self.URL).status_code == 401
        assert client_session.get(self.URL).status_code == 403
        # Produtos não são rota do assistente: exigem cadastro concluído (BE-028).
        assert workshop_session.get(self.URL).status_code == 403
