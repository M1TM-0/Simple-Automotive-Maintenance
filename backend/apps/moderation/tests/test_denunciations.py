"""BE-073: fila de denúncias, resolução com efeito sobre o conteúdo (DP-15) e ocultação de avaliação."""

import logging
import time
import uuid
from datetime import timedelta

import pytest
from apps.core.tests.factories import (
    AttendanceFactory,
    ClientFactory,
    DenunciationFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
    deliver_attendance,
    make_ready_workshop,
    make_review,
)
from apps.notifications.models import Notification
from apps.promotions.models import PromotionAdvertisement
from apps.reviews.models import Denunciation, Review
from django.db import connection
from django.utils import timezone

URL = "/api/admin/denunciations/"
pytestmark = pytest.mark.django_db


def detail(denunciation):
    return f"{URL}{denunciation.pk}/"


@pytest.fixture
def workshop():
    return make_ready_workshop()


@pytest.fixture
def review(workshop):
    author = ClientFactory(name="Bruno Carvalho Lima")
    budget, *_ = deliver_attendance(AttendanceFactory(client=author, workshop=workshop))
    return make_review(budget, comment="Comentário ofensivo")


@pytest.fixture
def reporter():
    return ClientFactory(name="Ana Maria Souza")


def denounce(reporter, **target):
    return DenunciationFactory(client=reporter, reason="offensive_language", **target)


def notifications_of(client):
    return list(
        Notification.objects.filter(client=client).values_list(
            "title", "message", "url"
        )
    )


# ------------------------------------------------------------------- fila


class TestQueue:
    def test_lists_oldest_first_with_reporter_and_content(
        self, staff_client, review, reporter, workshop
    ):
        promotion = PromotionFactory(workshop=workshop, title="Óleo grátis")
        advertisement = PromotionAdvertisementFactory(
            promotion=PromotionFactory(workshop=workshop, title="Pneus")
        )
        on_review = denounce(reporter, review=review, promotion=None)
        on_promotion = denounce(reporter, promotion=promotion)
        on_advertisement = denounce(
            reporter, promotion=None, advertisement=advertisement
        )

        response = staff_client.get(URL)

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 3
        assert [item["id"] for item in body["results"]] == [
            on_review.pk,
            on_promotion.pk,
            on_advertisement.pk,
        ]
        first = body["results"][0]
        assert first["target_type"] == "review" and first["target_id"] == str(review.pk)
        assert (
            first["status_denunciation"],
            first["moderation_decision"],
            first["date_resolution"],
        ) == (
            "pending",
            None,
            None,
        )
        assert first["reporter"] == {"id": reporter.pk, "name": "Ana Maria Souza"}
        assert first["content"] == {
            "type": "review",
            "id": str(review.pk),
            "status": "published",
            "workshop": {"id": workshop.pk, "name_fantasy": workshop.name_fantasy},
            "rating": 5,
            "comment": "Comentário ofensivo",
            "author_name": "Bruno Carvalho Lima",
        }
        assert body["results"][1]["content"] == {
            "type": "promotion",
            "id": str(promotion.pk),
            "status": "active",
            "workshop": {"id": workshop.pk, "name_fantasy": workshop.name_fantasy},
            "title": "Óleo grátis",
        }
        ad_content = body["results"][2]["content"]
        assert (
            ad_content["type"],
            ad_content["id_promotion"],
            ad_content["payment_status"],
        ) == (
            "advertisement",
            advertisement.promotion_id,
            "pending",
        )
        assert "email" not in str(body)

    def test_filters_by_status_and_target_type(self, staff_client, review, reporter):
        open_one = denounce(reporter, review=review, promotion=None)
        in_review = DenunciationFactory(status_denunciation="pending")
        Denunciation.objects.filter(pk=in_review.pk).update(
            status_denunciation="in_review"
        )
        resolved = DenunciationFactory()
        Denunciation.objects.filter(pk=resolved.pk).update(
            status_denunciation="dismissed", moderation_decision="ok"
        )

        open_ids = [
            i["id"]
            for i in staff_client.get(URL, {"status": "pending,in_review"}).json()[
                "results"
            ]
        ]
        review_ids = [
            i["id"]
            for i in staff_client.get(URL, {"target_type": "review"}).json()["results"]
        ]

        assert open_ids == [open_one.pk, in_review.pk]
        assert review_ids == [open_one.pk]

    @pytest.mark.parametrize(
        "params", [{"status": "pending,closed"}, {"target_type": "product"}]
    )
    def test_invalid_filter_is_400(self, staff_client, params):
        assert staff_client.get(URL, params).status_code == 400

    def test_query_count_does_not_grow_with_the_queue(
        self, staff_client, review, reporter, django_assert_max_num_queries
    ):
        denounce(reporter, review=review, promotion=None)
        DenunciationFactory(
            promotion=None, advertisement=PromotionAdvertisementFactory()
        )
        with django_assert_max_num_queries(6) as few:
            staff_client.get(URL)
        for _ in range(3):
            DenunciationFactory()
            DenunciationFactory(
                promotion=None, advertisement=PromotionAdvertisementFactory()
            )
        with django_assert_max_num_queries(len(few.captured_queries)):
            assert staff_client.get(URL).json()["count"] == 8

    def test_detail(self, staff_client, reporter):
        denunciation = DenunciationFactory(client=reporter)
        response = staff_client.get(detail(denunciation))
        assert response.status_code == 200
        assert response.json()["id"] == denunciation.pk
        assert staff_client.get(f"{URL}999999/").status_code == 404


# -------------------------------------------------------------- resolução


class TestModerate:
    def test_upheld_without_decision_is_400(self, staff_client, reporter):
        denunciation = DenunciationFactory(client=reporter)

        for payload in (
            {"status_denunciation": "upheld"},
            {"status_denunciation": "upheld", "moderation_decision": "  "},
        ):
            response = staff_client.patch(detail(denunciation), payload, format="json")
            assert response.status_code == 400
            assert "moderation_decision" in response.json()

        denunciation.refresh_from_db()
        assert denunciation.status_denunciation == "pending"

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"status_denunciation": "pending"}, "status_denunciation"),
            ({"status_denunciation": "closed"}, "status_denunciation"),
            ({}, "status_denunciation"),
            (
                {"status_denunciation": "dismissed", "moderation_decision": "x" * 2001},
                "moderation_decision",
            ),
        ],
    )
    def test_invalid_body_is_400(self, staff_client, reporter, payload, field):
        response = staff_client.patch(
            detail(DenunciationFactory(client=reporter)), payload, format="json"
        )
        assert response.status_code == 400
        assert field in response.json()

    def test_in_review_then_dismissed_notifies_the_reporter(
        self, staff_client, reporter, review, commit
    ):
        denunciation = denounce(reporter, review=review, promotion=None)

        response = staff_client.patch(
            detail(denunciation), {"status_denunciation": "in_review"}, format="json"
        )
        assert response.status_code == 200
        assert (
            response.json()["status_denunciation"],
            response.json()["date_resolution"],
        ) == ("in_review", None)
        assert (
            staff_client.patch(
                detail(denunciation),
                {"status_denunciation": "in_review"},
                format="json",
            ).status_code
            == 409
        )

        response = commit(
            staff_client.patch,
            detail(denunciation),
            {
                "status_denunciation": "dismissed",
                "moderation_decision": "Crítica legítima ao serviço.",
            },
            format="json",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status_denunciation"] == "dismissed"
        assert body["moderation_decision"] == "Crítica legítima ao serviço."
        assert body["date_resolution"] is not None
        review.refresh_from_db()
        assert review.status_review == "published"
        [(title, message, url)] = notifications_of(reporter)
        assert title == "Denúncia analisada"
        assert review.budget.workshop.name_fantasy in message and "mantido" in message
        assert "Crítica legítima" not in message and url is None

    def test_upheld_review_is_hidden_and_leaves_public_lists(
        self, staff_client, api_client, reporter, review, workshop, commit
    ):
        denunciation = denounce(reporter, review=review, promotion=None)
        public = f"/api/workshops/{workshop.pk}/reviews/"
        assert api_client.get(public).json()["count"] == 1

        response = commit(
            staff_client.patch,
            detail(denunciation),
            {
                "status_denunciation": "upheld",
                "moderation_decision": "Linguagem ofensiva.",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["content"]["status"] == "hidden"
        review.refresh_from_db()
        assert review.status_review == "hidden"
        assert api_client.get(public).json()["count"] == 0
        profile = api_client.get(f"/api/workshops/{workshop.pk}/").json()
        assert (profile["rating_avg"], profile["rating_count"]) == (None, 0)
        [(title, message, _)] = notifications_of(reporter)
        assert title == "Denúncia procedente" and "retirado do ar" in message

    def test_resolved_denunciation_is_409(self, staff_client, reporter):
        denunciation = DenunciationFactory(client=reporter)
        resolve = {
            "status_denunciation": "dismissed",
            "moderation_decision": "Sem violação.",
        }
        assert (
            staff_client.patch(detail(denunciation), resolve, format="json").status_code
            == 200
        )

        for payload in (
            {"status_denunciation": "upheld", "moderation_decision": "Mudei de ideia."},
            {"status_denunciation": "in_review"},
            resolve,
        ):
            response = staff_client.patch(detail(denunciation), payload, format="json")
            assert response.status_code == 409
            assert response.json() == {"detail": "Esta denúncia já foi resolvida."}

        denunciation.refresh_from_db()
        assert (denunciation.status_denunciation, denunciation.moderation_decision) == (
            "dismissed",
            "Sem violação.",
        )

    def test_upheld_promotion_is_deactivated_and_paid_advertisement_refunded(
        self, staff_client, reporter, workshop, commit
    ):
        promotion = PromotionFactory(workshop=workshop, title="Óleo grátis")
        paid = PromotionAdvertisementFactory(promotion=promotion, payment_status="paid")
        unpaid = PromotionAdvertisementFactory(promotion=promotion)
        denunciation = denounce(reporter, promotion=promotion)

        response = commit(
            staff_client.patch,
            detail(denunciation),
            {
                "status_denunciation": "upheld",
                "moderation_decision": "Propaganda enganosa.",
            },
            format="json",
        )

        assert response.status_code == 200
        promotion.refresh_from_db()
        assert promotion.status_promotion == "inactive"
        states = dict(
            PromotionAdvertisement.objects.filter(promotion=promotion).values_list(
                "pk", "payment_status"
            )
        )
        assert states == {paid.pk: "refunded", unpaid.pk: "pending"}
        assert set(
            PromotionAdvertisement.objects.filter(promotion=promotion).values_list(
                "status_advertisement", flat=True
            )
        ) == {"cancelled"}
        workshop_titles = sorted(
            Notification.objects.filter(workshop=workshop).values_list(
                "title", flat=True
            )
        )
        assert workshop_titles == [
            "Conteúdo retirado pela moderação",
            "Estorno da divulgação",
        ]
        assert notifications_of(reporter)[0][0] == "Denúncia procedente"

    def test_upheld_advertisement_is_cancelled_and_refunded(
        self, staff_client, reporter, workshop, commit
    ):
        promotion = PromotionFactory(workshop=workshop, title="Pneus")
        advertisement = PromotionAdvertisementFactory(
            promotion=promotion, payment_status="paid"
        )
        denunciation = denounce(reporter, promotion=None, advertisement=advertisement)

        response = commit(
            staff_client.patch,
            detail(denunciation),
            {
                "status_denunciation": "upheld",
                "moderation_decision": "Imagem imprópria.",
            },
            format="json",
        )

        assert response.status_code == 200
        advertisement.refresh_from_db()
        promotion.refresh_from_db()
        assert (advertisement.status_advertisement, advertisement.payment_status) == (
            "cancelled",
            "refunded",
        )
        assert promotion.status_promotion == "active"  # só a divulgação sai do ar
        messages = dict(
            Notification.objects.filter(workshop=workshop).values_list(
                "title", "message"
            )
        )
        assert (
            "divulgação da promoção “Pneus” foi cancelada"
            in messages["Conteúdo retirado pela moderação"]
        )
        assert "R$ 50,00" in messages["Estorno da divulgação"]

    def test_pending_can_be_resolved_directly_and_audit_has_the_transition(
        self, staff_client, reporter, caplog
    ):
        denunciation = DenunciationFactory(client=reporter)

        with caplog.at_level(logging.INFO, logger="sam.audit"):
            response = staff_client.patch(
                detail(denunciation),
                {"status_denunciation": "dismissed", "moderation_decision": "Ok."},
                format="json",
            )

        assert response.status_code == 200
        [record] = [r for r in caplog.records if r.name == "sam.audit"]
        assert record.getMessage() == "admin.denunciation.moderate"
        assert (
            record.target_type,
            record.target_id,
            record.from_status,
            record.to_status,
        ) == (
            "denunciation",
            str(denunciation.pk),
            "pending",
            "dismissed",
        )

    def test_access_matrix(
        self, api_client, client_session, ready_workshop_session, staff_client
    ):
        denunciation = DenunciationFactory()
        payload = {"status_denunciation": "in_review"}

        assert (
            api_client.patch(detail(denunciation), payload, format="json").status_code
            == 401
        )
        assert (
            client_session.patch(
                detail(denunciation), payload, format="json"
            ).status_code
            == 403
        )
        assert (
            ready_workshop_session.patch(
                detail(denunciation), payload, format="json"
            ).status_code
            == 403
        )
        assert (
            staff_client.patch(f"{URL}999999/", payload, format="json").status_code
            == 404
        )
        assert (
            staff_client.put(detail(denunciation), payload, format="json").status_code
            == 405
        )
        assert staff_client.delete(detail(denunciation)).status_code == 405
        denunciation.refresh_from_db()
        assert denunciation.status_denunciation == "pending"


@pytest.mark.django_db(transaction=True)
def test_upheld_on_expired_promotion_keeps_it_expired(staff_client, reporter):
    """Expirada é definitiva (trigger): a denúncia resolve sem tocar na promoção.
    Relógio real: cada requisição é uma transação, o NOW() do banco avança."""
    promotion = PromotionFactory(
        workshop=make_ready_workshop(),
        date_end=timezone.now() + timedelta(milliseconds=400),
    )
    time.sleep(0.6)
    with connection.cursor() as cursor:
        cursor.execute("SELECT expire_promotions()")
    denunciation = denounce(reporter, promotion=promotion)

    response = staff_client.patch(
        detail(denunciation),
        {"status_denunciation": "upheld", "moderation_decision": "Fraude."},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["content"]["status"] == "expired"
    promotion.refresh_from_db()
    assert promotion.status_promotion == "expired"


# ---------------------------------------------------- ocultar avaliação


class TestHideReview:
    def url(self, review):
        return f"/api/admin/reviews/{review.pk}/hide/"

    def test_hides_and_is_idempotent(self, staff_client, api_client, review, workshop):
        for _ in range(2):
            response = staff_client.post(self.url(review))
            assert response.status_code == 200
            body = response.json()
            assert (body["id"], body["status_review"]) == (str(review.pk), "hidden")
            assert body["workshop"] == {
                "id": workshop.pk,
                "name_fantasy": workshop.name_fantasy,
            }
            assert body["client_name"] == "Bruno Carvalho Lima"

        assert (
            api_client.get(f"/api/workshops/{workshop.pk}/reviews/").json()["count"]
            == 0
        )
        assert Review.objects.get(pk=review.pk).status_review == "hidden"

    def test_unknown_review_is_404(self, staff_client):
        assert (
            staff_client.post(f"/api/admin/reviews/{uuid.uuid4()}/hide/").status_code
            == 404
        )

    def test_access_matrix(self, api_client, client_session, review):
        assert api_client.post(self.url(review)).status_code == 401
        assert client_session.post(self.url(review)).status_code == 403
        assert Review.objects.get(pk=review.pk).status_review == "published"
