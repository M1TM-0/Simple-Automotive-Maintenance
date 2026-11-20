"""BE-059 (avaliar), BE-060 (avaliações recebidas e resposta) e BE-061 (denunciar)."""

import uuid

import pytest
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    ClientFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
    deliver_attendance,
    make_ready_workshop,
    make_review,
)
from apps.reviews.domain import author_display_name
from apps.reviews.models import Denunciation, Review


@pytest.fixture
def delivered_budget(client_account, ready_workshop):
    budget, *_ = deliver_attendance(
        AttendanceFactory(client=client_account, workshop=ready_workshop)
    )
    return budget


# ------------------------------------------------------------------ BE-059


@pytest.mark.django_db
class TestCreateReview:
    URL = "/api/reviews/"

    def test_delivered_attendance_can_be_reviewed(
        self, client_session, delivered_budget
    ):
        response = client_session.post(
            self.URL,
            {"id_budget": delivered_budget.pk, "rating": 5, "comment": "Ótimo serviço"},
            format="json",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["rating"], body["status_review"], body["id_attendance"]) == (
            5,
            "published",
            delivered_budget.attendance_id,
        )
        uuid.UUID(body["id"])

    def test_second_review_is_409(self, client_session, delivered_budget):
        payload = {"id_budget": delivered_budget.pk, "rating": 4}
        client_session.post(self.URL, payload, format="json")
        response = client_session.post(self.URL, payload, format="json")
        assert response.status_code == 409
        assert response.json() == {"detail": "Você já avaliou este atendimento."}

    def test_not_delivered_is_409_with_db_message(self, client_session, client_account):
        budget = BudgetFactory(attendance=AttendanceFactory(client=client_account))
        response = client_session.post(
            self.URL, {"id_budget": budget.pk, "rating": 3}, format="json"
        )
        assert response.status_code == 409
        assert "orçamento aprovado" in response.json()["detail"]

    def test_budget_of_another_client_is_404(self, client_session):
        budget, *_ = deliver_attendance(
            AttendanceFactory(workshop=make_ready_workshop())
        )
        assert (
            client_session.post(
                self.URL, {"id_budget": budget.pk, "rating": 5}, format="json"
            ).status_code
            == 404
        )
        assert not Review.objects.exists()

    @pytest.mark.parametrize(
        ("field", "value"), [("rating", 0), ("rating", 6), ("comment", "x" * 501)]
    )
    def test_invalid_input_is_400(self, client_session, delivered_budget, field, value):
        payload = {"id_budget": delivered_budget.pk, "rating": 5, field: value}
        response = client_session.post(self.URL, payload, format="json")
        assert response.status_code == 400
        assert field in response.json()

    def test_access_matrix(self, api_client, ready_workshop_session):
        assert api_client.post(self.URL, {}, format="json").status_code == 401
        assert (
            ready_workshop_session.post(self.URL, {}, format="json").status_code == 403
        )


# ------------------------------------------------------------------ BE-060


@pytest.mark.django_db
class TestWorkshopReviews:
    def test_lists_all_statuses_with_abbreviated_author(
        self, ready_workshop_session, ready_workshop
    ):
        client = ClientFactory(name="Ana Maria Souza")
        budgets = [
            deliver_attendance(
                AttendanceFactory(client=client, workshop=ready_workshop)
            )[0]
            for _ in range(2)
        ]
        make_review(budgets[0])
        make_review(budgets[1], status_review="hidden")
        make_review(
            deliver_attendance(AttendanceFactory(workshop=make_ready_workshop()))[0]
        )  # outra oficina

        rows = ready_workshop_session.get("/api/workshop/reviews/").json()["results"]

        assert sorted(r["status_review"] for r in rows) == ["hidden", "published"]
        assert {r["client_name"] for r in rows} == {"Ana S."}

    def test_response_is_saved_and_edit_updates_date(
        self, ready_workshop_session, ready_workshop
    ):
        review = make_review(
            deliver_attendance(AttendanceFactory(workshop=ready_workshop))[0]
        )
        url = f"/api/workshop/reviews/{review.pk}/response/"

        first = ready_workshop_session.post(
            url, {"workshop_response": "Obrigado!"}, format="json"
        ).json()
        second = ready_workshop_session.post(
            url, {"workshop_response": "Obrigado pela visita!"}, format="json"
        ).json()

        assert first["workshop_response"] == "Obrigado!"
        assert second["workshop_response"] == "Obrigado pela visita!"
        assert second["date_response"] > first["date_response"]

    @pytest.mark.parametrize("text", ["", "   ", "x" * 1001])
    def test_invalid_response_is_400(
        self, ready_workshop_session, ready_workshop, text
    ):
        review = make_review(
            deliver_attendance(AttendanceFactory(workshop=ready_workshop))[0]
        )
        response = ready_workshop_session.post(
            f"/api/workshop/reviews/{review.pk}/response/",
            {"workshop_response": text},
            format="json",
        )
        assert response.status_code == 400

    def test_hidden_review_cannot_be_answered(
        self, ready_workshop_session, ready_workshop
    ):
        review = make_review(
            deliver_attendance(AttendanceFactory(workshop=ready_workshop))[0],
            status_review="hidden",
        )
        response = ready_workshop_session.post(
            f"/api/workshop/reviews/{review.pk}/response/",
            {"workshop_response": "Oi"},
            format="json",
        )
        assert response.status_code == 409

    def test_review_of_another_workshop_is_404(self, ready_workshop_session):
        review = make_review(
            deliver_attendance(AttendanceFactory(workshop=make_ready_workshop()))[0]
        )
        response = ready_workshop_session.post(
            f"/api/workshop/reviews/{review.pk}/response/",
            {"workshop_response": "Oi"},
            format="json",
        )
        assert response.status_code == 404

    def test_access_matrix(self, api_client, client_session, workshop_session):
        assert api_client.get("/api/workshop/reviews/").status_code == 401
        assert client_session.get("/api/workshop/reviews/").status_code == 403
        assert workshop_session.get("/api/workshop/reviews/").status_code == 403


def test_author_display_name():
    assert author_display_name("Ana Maria Souza") == "Ana S."
    assert author_display_name("  Joao  ") == "Joao"
    assert author_display_name("") is None


# ------------------------------------------------------------------ BE-061


@pytest.mark.django_db
class TestDenunciations:
    URL = "/api/denunciations/"

    def targets(self):
        review = make_review(
            deliver_attendance(AttendanceFactory(workshop=make_ready_workshop()))[0]
        )
        advertisement = PromotionAdvertisementFactory()
        return {
            "review": str(review.pk),
            "promotion": str(PromotionFactory().pk),
            "advertisement": str(advertisement.pk),
        }

    @pytest.mark.parametrize("target_type", ["review", "promotion", "advertisement"])
    def test_creates_pending_for_each_target(self, client_session, target_type):
        target_id = self.targets()[target_type]

        response = client_session.post(
            self.URL,
            {"target_type": target_type, "target_id": target_id, "reason": "spam"},
            format="json",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert (
            body["status_denunciation"],
            body["target_type"],
            body["target_id"],
        ) == ("pending", target_type, target_id)

    def test_duplicate_open_denunciation_is_409(self, client_session):
        payload = {
            "target_type": "promotion",
            "target_id": self.targets()["promotion"],
            "reason": "fraud",
        }
        client_session.post(self.URL, payload, format="json")
        response = client_session.post(self.URL, payload, format="json")
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Você já denunciou este conteúdo e ele está em análise."
        }

    def test_other_without_description_is_400(self, client_session):
        payload = {
            "target_type": "promotion",
            "target_id": self.targets()["promotion"],
            "reason": "other",
            "description": "  ",
        }
        response = client_session.post(self.URL, payload, format="json")
        assert response.status_code == 400
        assert "description" in response.json()

    @pytest.mark.parametrize(
        ("target_type", "target_id"),
        [
            ("review", "nao-e-uuid"),
            ("review", str(uuid.uuid4())),
            ("promotion", "999999"),
            ("advertisement", "abc"),
        ],
    )
    def test_missing_target_is_404(self, client_session, target_type, target_id):
        response = client_session.post(
            self.URL,
            {"target_type": target_type, "target_id": target_id, "reason": "spam"},
            format="json",
        )
        assert response.status_code == 404
        assert not Denunciation.objects.exists()

    def test_hidden_review_is_404(self, client_session):
        review = make_review(
            deliver_attendance(AttendanceFactory(workshop=make_ready_workshop()))[0],
            status_review="hidden",
        )
        response = client_session.post(
            self.URL,
            {"target_type": "review", "target_id": str(review.pk), "reason": "spam"},
            format="json",
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        ("field", "value"),
        [("reason", "chato"), ("target_type", "workshop"), ("description", "x" * 501)],
    )
    def test_invalid_fields_are_400(self, client_session, field, value):
        payload = {
            "target_type": "promotion",
            "target_id": self.targets()["promotion"],
            "reason": "spam",
            field: value,
        }
        response = client_session.post(self.URL, payload, format="json")
        assert response.status_code == 400
        assert field in response.json()

    def test_access_matrix(self, api_client, ready_workshop_session):
        assert api_client.post(self.URL, {}, format="json").status_code == 401
        assert (
            ready_workshop_session.post(self.URL, {}, format="json").status_code == 403
        )
