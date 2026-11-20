"""BE-066 (produtos, promoções e avaliações públicas da oficina) e BE-068 (no ar)."""

import time
from datetime import timedelta

import pytest
from apps.accounts.models import AccountStatus
from apps.core.tests.factories import (
    AttendanceFactory,
    ClientFactory,
    PagWorkshopFactory,
    ProductFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
    WorkshopServiceFactory,
    deliver_attendance,
    make_ready_workshop,
)
from apps.reviews.models import Review
from django.utils import timezone

PROMOTIONS_URL = "/api/promotions/"


def products_url(pk):
    return f"/api/workshops/{pk}/products/"


def workshop_promotions_url(pk):
    return f"/api/workshops/{pk}/promotions/"


def reviews_url(pk):
    return f"/api/workshops/{pk}/reviews/"


def ago(**kwargs):
    return timezone.now() - timedelta(**kwargs)


def ahead(**kwargs):
    return timezone.now() + timedelta(**kwargs)


def running_ad(promotion, **kwargs):
    """Divulgação paga, ativa e dentro do período (no ar)."""
    defaults = {
        "promotion": promotion,
        "date_start": ago(hours=1),
        "date_end": ahead(days=2),
        "payment_status": "paid",
        "status_advertisement": "active",
        "image_url": "promotions/ad.png",
    }
    defaults.update(kwargs)
    return PromotionAdvertisementFactory(**defaults)


@pytest.fixture
def workshop(db):
    return make_ready_workshop()


# ------------------------------------------------------------------ BE-066


@pytest.mark.django_db
class TestPublicProducts:
    def test_only_active_products_for_visitor(self, api_client, workshop):
        visible = ProductFactory(
            workshop=workshop, name="Filtro de óleo", photo="products/f.png"
        )
        unavailable = ProductFactory(
            workshop=workshop, name="Pastilha", disponibility=False
        )
        ProductFactory(workshop=workshop, name="Inativo", active=False)
        ProductFactory(name="De outra oficina")

        response = api_client.get(products_url(workshop.pk))

        assert response.status_code == 200
        body = response.json()
        assert [p["id"] for p in body["results"]] == [visible.pk, unavailable.pk]
        item = body["results"][0]
        assert set(item) == {
            "id",
            "name",
            "description",
            "category",
            "brand",
            "price",
            "disponibility",
            "photo",
        }
        assert item["price"] == "30.00"
        assert item["photo"].endswith("/media/products/f.png")
        assert body["results"][1]["disponibility"] is False

    @pytest.mark.parametrize(
        "url", [products_url, workshop_promotions_url, reviews_url]
    )
    def test_non_public_workshop_is_404(self, api_client, url):
        blocked = make_ready_workshop()
        blocked.status = AccountStatus.BLOCKED
        blocked.save(update_fields=["status"])
        in_wizard = PagWorkshopFactory().workshop

        assert api_client.get(url(blocked.pk)).status_code == 404
        assert api_client.get(url(in_wizard.pk)).status_code == 404
        assert api_client.get(url(999_999)).status_code == 404


@pytest.mark.django_db
class TestPublicWorkshopPromotions:
    def test_only_valid_promotions_in_public_shape(self, api_client, workshop):
        service = workshop.services.first()
        valid = PromotionFactory(
            workshop=workshop,
            title="Óleo -15%",
            workshop_service=service,
            image_url="promotions/p.png",
        )
        PromotionFactory(workshop=workshop, status_promotion="inactive")
        PromotionFactory(
            workshop=workshop, date_start=ahead(days=1), date_end=ahead(days=5)
        )  # agendada
        PromotionFactory(title="De outra oficina")

        body = api_client.get(workshop_promotions_url(workshop.pk)).json()

        assert body["count"] == 1
        item = body["results"][0]
        assert item["id"] == item["id_promotion"] == valid.pk
        assert item["kind"] == "promotion"
        assert item["title"] == "Óleo -15%"
        assert item["image_url"].endswith("/media/promotions/p.png")
        assert item["workshop"] == {
            "id": workshop.pk,
            "name_fantasy": workshop.name_fantasy,
        }
        assert item["target_name"] == service.service.name
        assert (item["type_discount"], item["discount_value"]) == (
            "percentage",
            "10.00",
        )
        assert (item["is_valid_now"], item["is_running_now"]) == (True, None)

    def test_advertisements_are_not_listed_in_workshop_promotions(
        self, api_client, workshop
    ):
        running_ad(PromotionFactory(workshop=workshop))

        body = api_client.get(workshop_promotions_url(workshop.pk)).json()

        assert [i["kind"] for i in body["results"]] == ["promotion"]


@pytest.mark.django_db
class TestPublicReviews:
    def make(self, workshop, rating, status="published", **kwargs):
        client = ClientFactory(name="Ana Souza Lima")
        budget, *_ = deliver_attendance(
            AttendanceFactory(workshop=workshop, client=client)
        )
        return Review.objects.create(
            budget=budget, rating=rating, status_review=status, **kwargs
        )

    def test_only_published_with_short_author_name(self, api_client, workshop):
        published = self.make(
            workshop,
            5,
            comment="Ótimo",
            workshop_response="Obrigado!",
            date_response=timezone.now(),
        )
        self.make(workshop, 1, status="hidden")
        self.make(workshop, 2, status="under_review")

        body = api_client.get(reviews_url(workshop.pk)).json()

        assert body["count"] == 1
        item = body["results"][0]
        assert item["id"] == str(published.pk)
        assert item["client_name"] == "Ana L."
        assert (item["rating"], item["comment"], item["workshop_response"]) == (
            5,
            "Ótimo",
            "Obrigado!",
        )
        for private in ("id_budget", "id_attendance", "status_review"):
            assert private not in item
        assert "Souza" not in str(body)

    def test_newest_first(self, api_client, workshop):
        older = self.make(workshop, 3)
        newer = self.make(workshop, 4)
        Review.objects.filter(pk=older.pk).update(date_creation=ago(days=3))

        ids = [
            i["id"] for i in api_client.get(reviews_url(workshop.pk)).json()["results"]
        ]

        assert ids == [str(newer.pk), str(older.pk)]


# ------------------------------------------------------------------ BE-068


@pytest.mark.django_db
class TestOnAir:
    def test_visitor_gets_200_without_login_and_cache_header(self, api_client):
        response = api_client.get(PROMOTIONS_URL, {"active": "true"})

        assert response.status_code == 200
        assert response.json() == {
            "count": 0,
            "next": None,
            "previous": None,
            "results": [],
        }
        assert "max-age=30" in response["Cache-Control"]

    def test_running_ads_first_then_valid_promotions_by_end_date(
        self, api_client, workshop
    ):
        late = PromotionFactory(
            workshop=workshop, title="Termina depois", date_end=ahead(days=20)
        )
        soon = PromotionFactory(
            workshop=workshop, title="Termina antes", date_end=ahead(days=3)
        )
        ad = running_ad(late)

        items = api_client.get(PROMOTIONS_URL, {"active": "true"}).json()["results"]

        assert [(i["kind"], i["id"]) for i in items] == [
            ("advertisement", ad.pk),
            ("promotion", soon.pk),
            ("promotion", late.pk),
        ]
        first = items[0]
        assert first["id_promotion"] == late.pk
        assert first["title"] == "Termina depois"
        assert first["image_url"].endswith("/media/promotions/ad.png")
        assert (first["is_valid_now"], first["is_running_now"]) == (True, True)
        assert first["workshop"] == {
            "id": workshop.pk,
            "name_fantasy": workshop.name_fantasy,
        }

    def test_inactive_promotion_does_not_appear(self, api_client, workshop):
        PromotionFactory(workshop=workshop, status_promotion="inactive")

        assert api_client.get(PROMOTIONS_URL).json()["count"] == 0

    def test_pending_or_unpaid_advertisement_does_not_appear(
        self, api_client, workshop
    ):
        promotion = PromotionFactory(workshop=workshop)
        PromotionAdvertisementFactory(promotion=promotion)  # pending/pending

        kinds = [i["kind"] for i in api_client.get(PROMOTIONS_URL).json()["results"]]

        assert kinds == ["promotion"]

    def test_only_public_workshops(self, api_client):
        blocked = make_ready_workshop()
        PromotionFactory(workshop=blocked)
        running_ad(PromotionFactory(workshop=blocked))
        blocked.status = AccountStatus.BLOCKED
        blocked.save(update_fields=["status"])
        in_wizard = PagWorkshopFactory().workshop
        PromotionFactory(workshop=in_wizard)

        assert api_client.get(PROMOTIONS_URL).json()["count"] == 0

    def test_target_name_of_product_promotion(self, api_client, workshop):
        product = ProductFactory(workshop=workshop, name="Filtro de ar")
        promotion = PromotionFactory(workshop=workshop, product=product)
        running_ad(promotion)

        items = api_client.get(PROMOTIONS_URL).json()["results"]

        assert {i["target_name"] for i in items} == {"Filtro de ar"}

    def test_target_name_of_custom_service_advertisement(self, api_client, workshop):
        custom = WorkshopServiceFactory(
            workshop=workshop,
            service=None,
            name_local="Polimento",
            status_solicitation="pending",
            suggested_category_id=1,
        )
        running_ad(PromotionFactory(workshop=workshop, workshop_service=custom))

        items = api_client.get(PROMOTIONS_URL).json()["results"]

        assert {i["target_name"] for i in items} == {"Polimento"}


@pytest.mark.django_db(transaction=True)
class TestOnAirWithRealClock:
    """`NOW()` do banco é o início da transação: cada requisição é uma transação própria."""

    def test_active_advertisement_outside_its_period_disappears(self, api_client):
        workshop = make_ready_workshop()
        promotion = PromotionFactory(workshop=workshop, date_end=ahead(days=5))
        running_ad(promotion, date_end=ahead(milliseconds=500))
        assert [
            i["kind"] for i in api_client.get(PROMOTIONS_URL).json()["results"]
        ] == [
            "advertisement",
            "promotion",
        ]

        time.sleep(0.7)

        assert [
            i["kind"] for i in api_client.get(PROMOTIONS_URL).json()["results"]
        ] == ["promotion"]

    def test_promotion_past_its_end_disappears_before_the_expiration_job(
        self, api_client
    ):
        workshop = make_ready_workshop()
        promotion = PromotionFactory(
            workshop=workshop, date_end=ahead(milliseconds=500)
        )
        assert api_client.get(PROMOTIONS_URL).json()["count"] == 1

        time.sleep(0.7)

        promotion.refresh_from_db()
        assert promotion.status_promotion == "active"  # a rotina ainda não rodou
        assert api_client.get(PROMOTIONS_URL).json()["count"] == 0
        assert api_client.get(workshop_promotions_url(workshop.pk)).json()["count"] == 0
