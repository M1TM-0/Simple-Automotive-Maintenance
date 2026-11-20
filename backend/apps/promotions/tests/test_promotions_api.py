"""BE-063 (promoções da oficina) e BE-064 (divulgação paga)."""

import time
from datetime import timedelta

import pytest
from apps.core.tests.factories import (
    ClientFactory,  # noqa: F401
    PagWorkshopFactory,
    ProductFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
    WorkshopServiceFactory,
    fake_image_upload,
    jpeg_upload,
    make_ready_workshop,
    stored_name,
)
from apps.promotions.models import Promotion, PromotionAdvertisement
from django.core.files.storage import default_storage
from django.db import connection
from django.utils import timezone

URL = "/api/workshop/promotions/"


def iso(delta):
    return (timezone.now() + delta).isoformat()


def promo_payload(**overrides):
    data = {
        "title": "Semana do óleo",
        "description": "",
        "type_discount": "percentage",
        "discount_value": "15",
        "date_start": iso(-timedelta(hours=1)),
        "date_end": iso(timedelta(days=10)),
        "status_promotion": "active",
        "id_workshop_service": "",
        "id_product": "",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ BE-063


@pytest.mark.django_db
class TestPromotions:
    def test_create_with_service_target_and_image(
        self, ready_workshop_session, ready_workshop
    ):
        service = ready_workshop.services.first()

        response = ready_workshop_session.post(
            URL,
            promo_payload(id_workshop_service=service.pk, image=jpeg_upload()),
            format="multipart",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["target_name"] == service.service.name
        assert (body["id_product"], body["description"]) == (None, None)
        assert (
            body["status_promotion"],
            body["effective_status"],
            body["is_valid_now"],
        ) == ("active", "active", True)
        assert body["image_url"].startswith("http://testserver/media/promotions/")

    def test_product_target_name(self, ready_workshop_session, ready_workshop):
        product = ProductFactory(workshop=ready_workshop, name="Filtro de ar")
        body = ready_workshop_session.post(
            URL, promo_payload(id_product=product.pk), format="multipart"
        ).json()
        assert body["target_name"] == "Filtro de ar"

    @pytest.mark.parametrize(
        ("overrides", "field"),
        [
            ({"discount_value": "120"}, "discount_value"),
            ({"discount_value": "0"}, "discount_value"),
            ({"type_discount": "bonus"}, "type_discount"),
            ({"date_end": iso(-timedelta(days=2))}, "date_end"),
            ({"status_promotion": "expired"}, "status_promotion"),
            ({"title": "  "}, "title"),
            ({"image": fake_image_upload()}, "image"),
        ],
    )
    def test_invalid_fields_are_400(self, ready_workshop_session, overrides, field):
        response = ready_workshop_session.post(
            URL, promo_payload(**overrides), format="multipart"
        )
        assert response.status_code == 400
        assert field in response.json()
        assert not Promotion.objects.exists()

    def test_fixed_discount_above_100_is_allowed(self, ready_workshop_session):
        response = ready_workshop_session.post(
            URL,
            promo_payload(type_discount="fixed", discount_value="150"),
            format="multipart",
        )
        assert response.status_code == 201

    def test_service_and_product_together_is_400(
        self, ready_workshop_session, ready_workshop
    ):
        product = ProductFactory(workshop=ready_workshop)
        service = ready_workshop.services.first()
        response = ready_workshop_session.post(
            URL,
            promo_payload(id_workshop_service=service.pk, id_product=product.pk),
            format="multipart",
        )
        assert response.status_code == 400
        assert "id_workshop_service" in response.json()

    def test_target_of_another_workshop_is_400(self, ready_workshop_session):
        other = make_ready_workshop()
        response = ready_workshop_session.post(
            URL,
            promo_payload(id_product=ProductFactory(workshop=other).pk),
            format="multipart",
        )
        assert response.status_code == 400
        assert "id_product" in response.json()

    def test_active_promotion_with_past_end_is_400(self, ready_workshop_session):
        response = ready_workshop_session.post(
            URL,
            promo_payload(
                date_start=iso(-timedelta(days=5)), date_end=iso(-timedelta(days=1))
            ),
            format="multipart",
        )
        assert response.status_code == 400
        assert "date_end" in response.json()

    def test_scheduled_and_inactive_effective_status(self, ready_workshop_session):
        scheduled = ready_workshop_session.post(
            URL,
            promo_payload(
                date_start=iso(timedelta(days=2)), date_end=iso(timedelta(days=5))
            ),
            format="multipart",
        ).json()
        inactive = ready_workshop_session.post(
            URL, promo_payload(status_promotion="inactive"), format="multipart"
        ).json()

        assert (scheduled["effective_status"], scheduled["is_valid_now"]) == (
            "scheduled",
            False,
        )
        assert (inactive["effective_status"], inactive["is_valid_now"]) == (
            "inactive",
            False,
        )

    def test_patch_deactivates_and_removes_image(
        self, ready_workshop_session, ready_workshop, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            created = ready_workshop_session.post(
                URL, promo_payload(image=jpeg_upload()), format="multipart"
            ).json()
        image = stored_name(created["image_url"])

        with django_capture_on_commit_callbacks(execute=True):
            response = ready_workshop_session.patch(
                f"{URL}{created['id']}/",
                {"status_promotion": "inactive", "title": "Nova", "image": ""},
                format="multipart",
            )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert (body["title"], body["effective_status"], body["image_url"]) == (
            "Nova",
            "inactive",
            None,
        )
        assert not default_storage.exists(image)

    def test_patch_validates_merged_values(self, ready_workshop_session):
        created = ready_workshop_session.post(
            URL,
            promo_payload(type_discount="fixed", discount_value="150"),
            format="multipart",
        ).json()
        response = ready_workshop_session.patch(
            f"{URL}{created['id']}/",
            {"type_discount": "percentage"},
            format="multipart",
        )
        assert response.status_code == 400
        assert "discount_value" in response.json()

    def test_deactivation_cancels_pending_advertisement(
        self, ready_workshop_session, ready_workshop
    ):
        promotion = PromotionFactory(workshop=ready_workshop)
        ad = PromotionAdvertisementFactory(promotion=promotion)
        ready_workshop_session.patch(
            f"{URL}{promotion.pk}/",
            {"status_promotion": "inactive"},
            format="multipart",
        )
        ad.refresh_from_db()
        assert ad.status_advertisement == "cancelled"

    def test_list_and_isolation(self, ready_workshop_session, ready_workshop):
        mine = PromotionFactory(workshop=ready_workshop)
        other = PromotionFactory(workshop=make_ready_workshop())

        rows = ready_workshop_session.get(URL).json()["results"]

        assert [row["id"] for row in rows] == [mine.pk]
        assert (
            ready_workshop_session.patch(
                f"{URL}{other.pk}/", {"title": "x"}, format="multipart"
            ).status_code
            == 404
        )

    def test_access_matrix(self, api_client, client_session, workshop_session):
        assert api_client.get(URL).status_code == 401
        assert client_session.get(URL).status_code == 403
        assert workshop_session.get(URL).status_code == 403


@pytest.mark.django_db(transaction=True)
class TestPromotionValidityWithRealClock:
    """O banco calcula a vigência com NOW() (início da transação): cada requisição
    abaixo é uma transação própria, então o relógio avança de verdade."""

    def test_past_end_is_expired_even_before_the_job(self, account_session):
        workshop = make_ready_workshop()
        api = account_session(workshop, "workshop")
        promotion = PromotionFactory(
            workshop=workshop, date_end=timezone.now() + timedelta(milliseconds=400)
        )
        time.sleep(0.6)

        row = api.get(URL).json()["results"][0]

        assert (
            row["status_promotion"],
            row["effective_status"],
            row["is_valid_now"],
        ) == ("active", "expired", False)
        response = api.patch(
            f"{URL}{promotion.pk}/", {"title": "Reaproveitar"}, format="multipart"
        )
        assert response.status_code == 409
        assert "crie uma nova promoção" in response.json()["detail"]

        with connection.cursor() as cursor:
            cursor.execute("SELECT expire_promotions()")
        assert (
            api.patch(
                f"{URL}{promotion.pk}/",
                {"status_promotion": "active"},
                format="multipart",
            ).status_code
            == 409
        )


# ------------------------------------------------------------------ BE-064


@pytest.mark.django_db
class TestAdvertisements:
    def url(self, promotion):
        return f"{URL}{promotion.pk}/advertisements/"

    def test_request_is_pending_with_server_price(
        self, ready_workshop_session, ready_workshop, settings
    ):
        settings.SAM_ADVERTISING_PRICE_PER_DAY = "12.50"
        promotion = PromotionFactory(workshop=ready_workshop)
        start = timezone.now() + timedelta(hours=1)

        response = ready_workshop_session.post(
            self.url(promotion),
            {
                "image": jpeg_upload(),
                "date_start": start.isoformat(),
                "date_end": (start + timedelta(days=2, hours=1)).isoformat(),
                "advertising_price": "0.01",
                "payment_status": "paid",
                "status_advertisement": "active",
            },
            format="multipart",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["advertising_price"] == "37.50"  # 3 diárias × R$ 12,50
        assert (
            body["payment_status"],
            body["status_advertisement"],
            body["is_running_now"],
        ) == ("pending", "pending", False)
        assert ready_workshop_session.get(self.url(promotion)).json()["count"] == 1

    def test_period_outside_promotion_is_400(
        self, ready_workshop_session, ready_workshop
    ):
        promotion = PromotionFactory(workshop=ready_workshop)
        response = ready_workshop_session.post(
            self.url(promotion),
            {
                "image": jpeg_upload(),
                "date_start": iso(timedelta(hours=1)),
                "date_end": iso(timedelta(days=30)),
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "O período da divulgação deve estar contido no período da promoção."
        }
        assert not PromotionAdvertisement.objects.exists()

    def test_inactive_promotion_is_409(self, ready_workshop_session, ready_workshop):
        promotion = PromotionFactory(
            workshop=ready_workshop, status_promotion="inactive"
        )
        response = ready_workshop_session.post(
            self.url(promotion),
            {
                "image": jpeg_upload(),
                "date_start": iso(timedelta(hours=1)),
                "date_end": iso(timedelta(days=2)),
            },
            format="multipart",
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            (
                {
                    "date_start": iso(timedelta(days=2)),
                    "date_end": iso(timedelta(days=1)),
                },
                "date_end",
            ),
            (
                {
                    "date_start": iso(timedelta(hours=1)),
                    "date_end": iso(timedelta(days=1)),
                    "image": None,
                },
                "image",
            ),
        ],
    )
    def test_invalid_request_is_400(
        self, ready_workshop_session, ready_workshop, payload, field
    ):
        promotion = PromotionFactory(workshop=ready_workshop)
        data = {"image": jpeg_upload(), **payload}
        data = {k: v for k, v in data.items() if v is not None}
        response = ready_workshop_session.post(
            self.url(promotion), data, format="multipart"
        )
        assert response.status_code == 400
        assert field in response.json()

    def test_promotion_of_another_workshop_is_404(self, ready_workshop_session):
        other = PromotionFactory(workshop=PagWorkshopFactory().workshop)
        WorkshopServiceFactory(workshop=other.workshop)
        assert ready_workshop_session.get(self.url(other)).status_code == 404
        response = ready_workshop_session.post(
            self.url(other),
            {
                "image": jpeg_upload(),
                "date_start": iso(timedelta(hours=1)),
                "date_end": iso(timedelta(days=1)),
            },
            format="multipart",
        )
        assert response.status_code == 404
