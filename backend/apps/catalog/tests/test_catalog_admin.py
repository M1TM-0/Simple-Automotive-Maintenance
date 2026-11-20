"""BE-075: curadoria do catálogo global e dos pontos de interesse no Django Admin."""

import pytest
from apps.accounts.models import Workshop
from apps.catalog.models import Service, ServiceCategory
from apps.core.tests.factories import PointOfInterestFactory, WorkshopFactory
from apps.workshops.models import PointOfInterest
from django.test import Client as BrowserClient

pytestmark = pytest.mark.django_db

SERVICES = "/admin/catalog/service/"
CATEGORIES = "/admin/catalog/servicecategory/"
POIS = "/admin/workshops/pointofinterest/"


@pytest.fixture
def staff_browser(django_user_model):
    browser = BrowserClient()
    browser.force_login(
        django_user_model.objects.create_superuser(
            "chefe", "chefe@exemplo.com", "SenhaAdmin123"
        )
    )
    return browser


def catalog_names(api, q):
    return [
        item["name"] for item in api.get("/api/services/", {"q": q}).json()["results"]
    ]


class TestServices:
    def test_create_stores_a_clean_name_and_shows_in_the_catalog(
        self, staff_browser, api_client
    ):
        category = ServiceCategory.objects.get(name="Motor")

        response = staff_browser.post(
            f"{SERVICES}add/",
            {
                "name": "  Limpeza   de bicos  ",
                "description": "Ultrassom",
                "category": category.pk,
                "active": "on",
            },
        )

        assert response.status_code == 302
        service = Service.objects.get(name="Limpeza de bicos")
        assert (service.category_id, service.active) == (category.pk, True)
        assert "Limpeza de bicos" in catalog_names(api_client, "limpeza de bicos")

    def test_duplicate_normalized_name_is_a_form_error(self, staff_browser):
        category = ServiceCategory.objects.get(name="Motor")
        before = Service.objects.count()

        response = staff_browser.post(
            f"{SERVICES}add/", {"name": "TROCA DE ÓLEO", "category": category.pk}
        )

        assert response.status_code == 200
        assert "Já existe um serviço com este nome" in response.content.decode()
        assert Service.objects.count() == before

    def test_editing_keeps_its_own_name_valid(self, staff_browser):
        service = Service.objects.get(name="Troca de óleo")

        response = staff_browser.post(
            f"{SERVICES}{service.pk}/change/",
            {
                "name": "Troca de óleo",
                "description": "Nova descrição",
                "category": service.category_id,
                "active": "on",
            },
        )

        assert response.status_code == 302
        service.refresh_from_db()
        assert service.description == "Nova descrição"

    def test_deactivated_service_leaves_the_public_catalog(
        self, staff_browser, api_client
    ):
        service = Service.objects.get(name="Troca de óleo")
        assert "Troca de óleo" in catalog_names(api_client, "troca de oleo")

        staff_browser.post(
            f"{SERVICES}{service.pk}/change/",
            {
                "name": service.name,
                "description": service.description or "",
                "category": service.category_id,
            },
        )

        assert Service.objects.get(pk=service.pk).active is False
        assert "Troca de óleo" not in catalog_names(api_client, "troca de oleo")

    def test_services_and_categories_cannot_be_deleted(self, staff_browser):
        service = Service.objects.first()
        category = ServiceCategory.objects.first()

        assert staff_browser.get(f"{SERVICES}{service.pk}/delete/").status_code == 403
        assert (
            staff_browser.get(f"{CATEGORIES}{category.pk}/delete/").status_code == 403
        )

    def test_create_category(self, staff_browser, api_client):
        response = staff_browser.post(
            f"{CATEGORIES}add/", {"name": "Blindagem", "description": ""}
        )

        assert response.status_code == 302
        names = [
            c["name"]
            for c in api_client.get("/api/service-categories/").json()["results"]
        ]
        assert "Blindagem" in names

    def test_duplicate_category_is_a_form_error(self, staff_browser):
        response = staff_browser.post(f"{CATEGORIES}add/", {"name": "Motor"})
        assert response.status_code == 200
        assert ServiceCategory.objects.filter(name="Motor").count() == 1


class TestPointsOfInterest:
    def valid(self, **overrides):
        return {
            "name": "Borracharia do Zé",
            "type": "borracharia",
            "latitude": "-5.0892",
            "longitude": "-42.8016",
            "address": "",
            "external_source": "",
            "external_id": "",
            **overrides,
        }

    def test_create_without_external_origin(self, staff_browser):
        assert staff_browser.post(f"{POIS}add/", self.valid()).status_code == 302
        point = PointOfInterest.objects.get(name="Borracharia do Zé")
        assert (point.external_source, point.external_id) == (None, None)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"latitude": "-91"},
            {"longitude": "181"},
            {"external_source": "osm"},
            {"external_id": "123"},
            {"type": "padaria"},
        ],
    )
    def test_invalid_data_is_a_form_error(self, staff_browser, overrides):
        response = staff_browser.post(f"{POIS}add/", self.valid(**overrides))
        assert response.status_code == 200
        assert not PointOfInterest.objects.exists()

    def test_duplicate_external_origin_is_a_form_error(self, staff_browser):
        PointOfInterestFactory(external_source="osm", external_id="n1")

        response = staff_browser.post(
            f"{POIS}add/", self.valid(external_source="osm", external_id="n1")
        )

        assert response.status_code == 200
        assert "já foi importado" in response.content.decode()

    def test_deleting_a_linked_point_only_unlinks_the_workshop(self, staff_browser):
        point = PointOfInterestFactory()
        workshop = WorkshopFactory(point_of_interest=point)

        response = staff_browser.post(f"{POIS}{point.pk}/delete/", {"post": "yes"})

        assert response.status_code == 302
        assert not PointOfInterest.objects.filter(pk=point.pk).exists()
        assert Workshop.objects.get(pk=workshop.pk).point_of_interest_id is None
