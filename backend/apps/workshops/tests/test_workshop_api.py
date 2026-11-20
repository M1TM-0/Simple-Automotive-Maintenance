"""BE-037 (conta), BE-038 (página), BE-039 (horários) e BE-040 (ponto no mapa)."""

import pytest
from apps.accounts.models import Workshop
from apps.core.tests.factories import (
    OperationHourFactory,
    PagWorkshopFactory,
    PointOfInterestFactory,
    fake_image_upload,
    jpeg_upload,
    stored_name,
)
from apps.workshops.models import OperationHour, PagWorkshop, PointOfInterest
from django.core.files.storage import default_storage


@pytest.fixture
def workshop(db):
    return PagWorkshopFactory().workshop


@pytest.fixture
def api(account_session, workshop):
    return account_session(workshop, "workshop")


# ------------------------------------------------------------------ BE-037


@pytest.mark.django_db
class TestWorkshopMe:
    URL = "/api/workshop/me/"

    def test_get_includes_point_page_and_setup(self, api, workshop):
        point = PointOfInterestFactory(name="Auto Center", address="Rua A, 10")
        Workshop.objects.filter(pk=workshop.pk).update(point_of_interest=point)

        body = api.get(self.URL).json()

        assert set(body) == {
            "id",
            "name_fantasy",
            "name_responsible",
            "email",
            "phone_number",
            "cnpj",
            "status",
            "setup_complete",
            "point",
            "page",
        }
        assert body["setup_complete"] is False
        assert body["point"] == {
            "id": point.pk,
            "name": "Auto Center",
            "type": "oficina",
            "address": "Rua A, 10",
            "latitude": -5.0912,
            "longitude": -42.8031,
        }
        assert body["page"]["description"] == "Página da oficina"
        assert body["page"]["photo_profile"].endswith(
            "/static/core/default-profile.png"
        )

    def test_point_is_null_without_link(self, api):
        assert api.get(self.URL).json()["point"] is None

    def test_patch_ignores_cnpj_email_status(self, api, workshop):
        original_cnpj, original_email = workshop.cnpj, workshop.email
        response = api.patch(
            self.URL,
            {
                "name_fantasy": "  Nova Oficina ",
                "name_responsible": "Maria",
                "phone_number": "",
                "cnpj": "11222333000181",
                "email": "hack@exemplo.com",
                "status": "blocked",
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        workshop.refresh_from_db()
        assert workshop.name_fantasy == "Nova Oficina"
        assert workshop.phone_number is None
        assert (workshop.cnpj, workshop.email) == (original_cnpj, original_email)
        assert workshop.status == "active"
        assert response.json()["name_responsible"] == "Maria"

    def test_blank_name_is_400(self, api):
        response = api.patch(self.URL, {"name_fantasy": "   "}, format="json")
        assert response.status_code == 400
        assert "name_fantasy" in response.json()

    def test_access_matrix(self, api_client, client_session):
        assert api_client.get(self.URL).status_code == 401
        assert client_session.get(self.URL).status_code == 403
        assert client_session.patch(self.URL, {}, format="json").status_code == 403


# ------------------------------------------------------------------ BE-038


@pytest.mark.django_db
class TestWorkshopPage:
    URL = "/api/workshop/page/"

    def test_upload_and_remove_banner(
        self, api, workshop, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            body = api.patch(
                self.URL,
                {"description": "Desde 1990", "photo_banner": jpeg_upload()},
                format="multipart",
            ).json()
        banner = stored_name(body["photo_banner"])
        assert body["description"] == "Desde 1990"
        assert default_storage.exists(banner)

        with django_capture_on_commit_callbacks(execute=True):
            response = api.patch(self.URL, {"photo_banner": ""}, format="multipart")

        assert response.status_code == 200
        assert response.json()["photo_banner"] is None
        assert not default_storage.exists(banner)

    def test_removed_profile_photo_returns_to_default(
        self, api, workshop, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            uploaded = api.patch(
                self.URL, {"photo_profile": jpeg_upload()}, format="multipart"
            ).json()
        old = stored_name(uploaded["photo_profile"])

        with django_capture_on_commit_callbacks(execute=True):
            body = api.patch(self.URL, {"photo_profile": ""}, format="multipart").json()

        assert body["photo_profile"].endswith("/static/core/default-profile.png")
        assert (
            PagWorkshop.objects.get(workshop=workshop).photo_profile
            == "default-profile.png"
        )
        assert not default_storage.exists(old)

    def test_non_image_is_400_on_field(self, api):
        response = api.patch(
            self.URL, {"photo_banner": fake_image_upload()}, format="multipart"
        )
        assert response.status_code == 400
        assert "photo_banner" in response.json()

    def test_description_limit(self, api):
        response = api.patch(self.URL, {"description": "x" * 1001}, format="json")
        assert response.status_code == 400
        assert "description" in response.json()

    def test_access_matrix(self, api_client, client_session):
        assert api_client.patch(self.URL, {}, format="json").status_code == 401
        assert client_session.patch(self.URL, {}, format="json").status_code == 403


# ------------------------------------------------------------------ BE-039


@pytest.mark.django_db
class TestOperationHours:
    URL = "/api/workshop/operation-hours/"

    def test_consecutive_intervals_are_accepted(self, api, workshop):
        payload = [
            {"day_of_week": 1, "opening_time": "12:00", "closing_time": "18:00"},
            {"day_of_week": 1, "opening_time": "08:00", "closing_time": "12:00"},
            {"day_of_week": 6, "opening_time": "08:00", "closing_time": "12:00"},
        ]

        response = api.put(self.URL, payload, format="json")

        assert response.status_code == 200, response.json()
        rows = response.json()["results"]
        assert [
            (r["day_of_week"], r["opening_time"], r["closing_time"]) for r in rows
        ] == [
            (1, "08:00", "12:00"),
            (1, "12:00", "18:00"),
            (6, "08:00", "12:00"),
        ]
        assert api.get(self.URL).json()["count"] == 3

    def test_overlap_is_400_and_previous_hours_remain(self, api, workshop):
        OperationHourFactory(
            workshop=workshop, day_of_week=2, opening_time="09:00", closing_time="17:00"
        )

        response = api.put(
            self.URL,
            [
                {"day_of_week": 1, "opening_time": "08:00", "closing_time": "12:00"},
                {"day_of_week": 1, "opening_time": "11:00", "closing_time": "14:00"},
            ],
            format="json",
        )

        assert response.status_code == 400
        assert "se sobrepõe" in response.json()["detail"]
        remaining = list(
            OperationHour.objects.filter(workshop=workshop).values_list(
                "day_of_week", flat=True
            )
        )
        assert remaining == [2]

    def test_empty_list_closes_workshop_without_touching_setup(self, api, workshop):
        OperationHourFactory(workshop=workshop)
        assert api.put(self.URL, [], format="json").json()["count"] == 0
        assert not OperationHour.objects.filter(workshop=workshop).exists()
        assert api.get("/api/workshop/me/").json()["setup_complete"] is False

    @pytest.mark.parametrize(
        ("item", "field"),
        [
            (
                {"day_of_week": 8, "opening_time": "08:00", "closing_time": "12:00"},
                "day_of_week",
            ),
            (
                {"day_of_week": 1, "opening_time": "12:00", "closing_time": "08:00"},
                "closing_time",
            ),
            (
                {"day_of_week": 1, "opening_time": "25:00", "closing_time": "26:00"},
                "opening_time",
            ),
        ],
    )
    def test_invalid_item_is_400_before_the_database(self, api, workshop, item, field):
        OperationHourFactory(workshop=workshop)
        response = api.put(self.URL, [item], format="json")
        assert response.status_code == 400
        assert response.json()[field][0].startswith("Horário 1:")
        assert OperationHour.objects.filter(workshop=workshop).count() == 1

    def test_body_must_be_a_list(self, api):
        assert api.put(self.URL, {"day_of_week": 1}, format="json").status_code == 400

    def test_lists_only_own_hours(self, api, workshop):
        OperationHourFactory(workshop=workshop)
        OperationHourFactory()
        assert api.get(self.URL).json()["count"] == 1

    def test_access_matrix(self, api_client, client_session):
        assert api_client.get(self.URL).status_code == 401
        assert client_session.put(self.URL, [], format="json").status_code == 403


# ------------------------------------------------------------------ BE-040


@pytest.mark.django_db
class TestPointOfInterest:
    SEARCH = "/api/points-of-interest/"
    LINK = "/api/workshop/point/"

    def test_search_marks_claimed_points(self, api, workshop):
        free = PointOfInterestFactory(
            name="Borracharia do Zé", address="Av. Frei Serafim"
        )
        taken = PointOfInterestFactory(name="Borracharia Central")
        PagWorkshopFactory(workshop__point_of_interest=taken)
        PointOfInterestFactory(name="Posto Ipiranga")

        rows = api.get(self.SEARCH, {"q": "BORRACHARIA"}).json()["results"]

        assert [(r["id"], r["claimed"]) for r in rows] == [
            (taken.pk, True),
            (free.pk, False),
        ]
        by_address = api.get(self.SEARCH, {"q": "frei serafim"}).json()["results"]
        assert [r["id"] for r in by_address] == [free.pk]

    def test_link_existing_point(self, api, workshop):
        point = PointOfInterestFactory()
        response = api.post(
            self.LINK, {"id_point_of_interest": point.pk}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["id"] == point.pk
        workshop.refresh_from_db()
        assert workshop.point_of_interest_id == point.pk
        mine = api.get(self.SEARCH).json()["results"][0]
        assert (mine["claimed"], mine["mine"]) == (False, True)

    def test_point_of_another_workshop_is_409(self, api):
        point = PointOfInterestFactory()
        PagWorkshopFactory(workshop__point_of_interest=point)

        response = api.post(
            self.LINK, {"id_point_of_interest": point.pk}, format="json"
        )

        assert response.status_code == 409
        assert "id_point_of_interest" in response.json()

    def test_create_new_point_and_link(self, api, workshop):
        response = api.post(
            self.LINK,
            {
                "name": " Oficina do João ",
                "type": "oficina",
                "latitude": -5.0892001,
                "longitude": "-42.80",
                "address": "Rua B",
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert (body["name"], body["latitude"], body["longitude"]) == (
            "Oficina do João",
            -5.0892,
            -42.8,
        )
        workshop.refresh_from_db()
        assert workshop.point_of_interest_id == body["id"]
        assert api.get("/api/workshop/me/").json()["point"]["id"] == body["id"]

    def test_changing_point_releases_the_previous(self, api, account_session):
        first, second = PointOfInterestFactory(), PointOfInterestFactory()
        api.post(self.LINK, {"id_point_of_interest": first.pk}, format="json")
        api.post(self.LINK, {"id_point_of_interest": second.pk}, format="json")

        other = account_session(PagWorkshopFactory().workshop, "workshop")
        response = other.post(
            self.LINK, {"id_point_of_interest": first.pk}, format="json"
        )

        assert response.status_code == 200
        assert PointOfInterest.objects.filter(pk=first.pk).exists()

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"name": "X", "latitude": 95, "longitude": 0}, "latitude"),
            ({"name": "X", "latitude": 0, "longitude": -181}, "longitude"),
            ({"name": "", "latitude": 0, "longitude": 0}, "name"),
            ({"name": "X", "latitude": 0}, "longitude"),
            ({"name": "X", "type": "nave", "latitude": 0, "longitude": 0}, "type"),
        ],
    )
    def test_invalid_new_point_is_400(self, api, payload, field):
        response = api.post(self.LINK, payload, format="json")
        assert response.status_code == 400
        assert field in response.json()
        assert not PointOfInterest.objects.exists()

    def test_missing_point_is_404(self, api):
        assert (
            api.post(
                self.LINK, {"id_point_of_interest": 999999}, format="json"
            ).status_code
            == 404
        )

    def test_access_matrix(self, api_client, client_session):
        assert api_client.get(self.SEARCH).status_code == 401
        assert client_session.get(self.SEARCH).status_code == 403
        assert client_session.post(self.LINK, {}, format="json").status_code == 403
