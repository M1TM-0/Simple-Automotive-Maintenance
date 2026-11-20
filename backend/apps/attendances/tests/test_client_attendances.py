"""BE-045 (solicitar), BE-046 (listar/detalhar), BE-047 (cancelar), BE-048 (aprovar/recusar)."""

from datetime import timedelta

import pytest
from apps.attendances.models import Attendance, Budget
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    PagWorkshopFactory,
    VehicleFactory,
    make_ready_workshop,
)
from apps.reviews.models import Review
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

URL = "/api/attendances/"


# ------------------------------------------------------------------ BE-045


@pytest.mark.django_db
class TestRequestAttendance:
    def test_creates_requested_with_session_client(
        self, client_session, client_account, ready_workshop
    ):
        vehicle = VehicleFactory(client=client_account)
        other_client = AttendanceFactory().client

        response = client_session.post(
            URL,
            {
                "id_workshop": ready_workshop.pk,
                "id_vehicle": vehicle.pk,
                "mileage_km": 61000,
                "observations": "Barulho na suspensão",
                "id_client": other_client.pk,
                "status_attendance": "approved",
            },
            format="json",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["status_attendance"] == "requested"
        assert body["workshop"]["id"] == ready_workshop.pk
        assert body["vehicle"]["id"] == vehicle.pk
        assert body["budgets"] == [] and body["review"] is None
        assert Attendance.objects.get(pk=body["id"]).client_id == client_account.pk

    def test_vehicle_of_another_client_is_400(self, client_session, ready_workshop):
        foreign = VehicleFactory()
        response = client_session.post(
            URL,
            {"id_workshop": ready_workshop.pk, "id_vehicle": foreign.pk},
            format="json",
        )
        assert response.status_code == 400
        assert "id_vehicle" in response.json()
        assert not Attendance.objects.exists()

    @pytest.mark.parametrize("case", ["blocked", "inactive", "no_setup", "missing"])
    def test_unavailable_workshop_is_400(self, client_session, client_account, case):
        if case == "missing":
            workshop_id = 999999
        elif case == "no_setup":
            workshop_id = PagWorkshopFactory().workshop.pk
        else:
            workshop = make_ready_workshop()
            workshop.__class__.objects.filter(pk=workshop.pk).update(status=case)
            workshop_id = workshop.pk
        vehicle = VehicleFactory(client=client_account)

        response = client_session.post(
            URL, {"id_workshop": workshop_id, "id_vehicle": vehicle.pk}, format="json"
        )

        assert response.status_code == 400
        assert response.json() == {
            "id_workshop": ["Oficina indisponível para atendimento."]
        }

    def test_observations_limit(self, client_session, client_account, ready_workshop):
        vehicle = VehicleFactory(client=client_account)
        response = client_session.post(
            URL,
            {
                "id_workshop": ready_workshop.pk,
                "id_vehicle": vehicle.pk,
                "observations": "x" * 1001,
            },
            format="json",
        )
        assert response.status_code == 400
        assert "observations" in response.json()

    def test_access_matrix(self, api_client, ready_workshop_session):
        assert api_client.post(URL, {}, format="json").status_code == 401
        assert ready_workshop_session.post(URL, {}, format="json").status_code == 403
        assert ready_workshop_session.get(URL).status_code == 403


# ------------------------------------------------------------------ BE-046


@pytest.mark.django_db
class TestListAndDetail:
    def test_status_filter_accepts_csv(self, client_session, flow):
        requested = flow.requested()
        budgeted, _ = flow.budgeted()
        delivered, _ = flow.delivered()
        AttendanceFactory()  # de outro cliente

        def ids(query):
            return [
                row["id"] for row in client_session.get(URL, query).json()["results"]
            ]

        assert ids({"status": "delivered"}) == [delivered.pk]
        assert sorted(ids({"status": "requested,budgeted"})) == sorted(
            [requested.pk, budgeted.pk]
        )
        assert sorted(ids({})) == sorted([requested.pk, budgeted.pk, delivered.pk])

    def test_invalid_status_is_400(self, client_session):
        response = client_session.get(URL, {"status": "requested,voando"})
        assert response.status_code == 400
        assert "status" in response.json()

    def test_vehicle_filter(self, client_session, flow, client_account):
        car = VehicleFactory(client=client_account)
        mine = flow.requested(vehicle=car)
        flow.requested()
        assert [
            row["id"]
            for row in client_session.get(URL, {"vehicle": car.pk}).json()["results"]
        ] == [mine.pk]

    def test_list_item_has_current_budget(self, client_session, flow):
        attendance, budget = flow.waiting()
        row = client_session.get(URL).json()["results"][0]
        assert row["id"] == attendance.pk
        assert row["budget"] == {
            "id": budget.pk,
            "status_budget": "pending",
            "total_price": "160.00",
            "date_validity": row["budget"]["date_validity"],
        }
        assert set(row["workshop"]) == {
            "id",
            "name_fantasy",
            "phone_number",
            "photo_profile",
        }
        assert set(row["vehicle"]) == {"id", "brand", "model", "plate", "year_model"}

    def test_detail_of_another_client_is_404(self, client_session):
        assert client_session.get(f"{URL}{AttendanceFactory().pk}/").status_code == 404

    def test_detail_has_budgets_items_and_review(self, client_session, flow):
        attendance, budget = flow.delivered()
        Review.objects.create(budget=budget, rating=4, comment="Bom")

        body = client_session.get(f"{URL}{attendance.pk}/").json()

        assert [b["id"] for b in body["budgets"]] == [budget.pk]
        items = body["budgets"][0]["items"]
        assert [
            (i["item_type"], i["subtotal"], i["execution_status"]) for i in items
        ] == [
            ("service", "100.00", "executed"),
            ("product", "60.00", "executed"),
        ]
        assert items[1]["id_service_item"] == items[0]["id"]
        assert body["review"]["rating"] == 4
        assert body["vehicle"]["history_shared"] is False

    def test_detail_uses_fixed_number_of_queries(self, client_session, flow):
        one, _ = flow.waiting()
        two, first = flow.budgeted()
        Budget.objects.filter(pk=first.pk).update(status_budget="cancelled")
        flow.budgeted(two)

        def count(attendance):
            with CaptureQueriesContext(connection) as ctx:
                assert client_session.get(f"{URL}{attendance.pk}/").status_code == 200
            return len(ctx.captured_queries)

        assert len(client_session.get(f"{URL}{two.pk}/").json()["budgets"]) == 2
        assert count(one) == count(two)


# ------------------------------------------------------------------ BE-047


@pytest.mark.django_db
class TestCancel:
    @pytest.mark.parametrize(
        "state", ["requested", "budgeted", "waiting", "approved", "in_progress"]
    )
    def test_cancel_from_open_states(self, client_session, flow, state):
        attendance, _ = flow.at(state)

        response = client_session.post(f"{URL}{attendance.pk}/cancel/")

        assert response.status_code == 200, response.json()
        assert response.json()["status_attendance"] == "canceled"
        statuses = set(
            Budget.objects.filter(attendance=attendance).values_list(
                "status_budget", flat=True
            )
        )
        assert statuses <= {"cancelled"}

    @pytest.mark.parametrize("state", ["completed", "delivered"])
    def test_cancel_after_completion_is_409(self, client_session, flow, state):
        attendance, _ = flow.at(state)
        response = client_session.post(f"{URL}{attendance.pk}/cancel/")
        assert response.status_code == 409
        assert "Transição de atendimento inválida" in response.json()["detail"]

    def test_cancel_twice_is_409(self, client_session, flow):
        attendance = flow.requested()
        client_session.post(f"{URL}{attendance.pk}/cancel/")
        assert client_session.post(f"{URL}{attendance.pk}/cancel/").status_code == 409

    def test_cancel_of_another_client_is_404(self, client_session):
        other = AttendanceFactory()
        assert client_session.post(f"{URL}{other.pk}/cancel/").status_code == 404
        other.refresh_from_db()
        assert other.status_attendance == "requested"


# ------------------------------------------------------------------ BE-048


@pytest.mark.django_db
class TestBudgetResponse:
    def test_approve_moves_attendance_to_approved(self, client_session, flow):
        attendance, budget = flow.waiting()

        response = client_session.post(f"/api/budgets/{budget.pk}/approve/")

        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["status_budget"] == "approved"
        assert body["date_response"] is not None
        assert body["attendance"] == {
            "id": attendance.pk,
            "status_attendance": "approved",
        }

    @pytest.mark.parametrize(
        ("action", "message"),
        [
            ("approve", "Este orçamento já foi aprovado."),
            ("reject", "Este orçamento já foi recusado."),
        ],
    )
    def test_answering_twice_is_409_and_notifies_once(
        self, client_session, flow, action, message, django_capture_on_commit_callbacks
    ):
        from apps.notifications.models import Notification

        attendance, budget = flow.waiting()
        url = f"/api/budgets/{budget.pk}/{action}/"
        with django_capture_on_commit_callbacks(execute=True):
            assert client_session.post(url).status_code == 200
        with django_capture_on_commit_callbacks(execute=True):
            second = client_session.post(url)

        assert second.status_code == 409
        assert second.json() == {"detail": message}
        assert Notification.objects.filter(workshop=attendance.workshop).count() == 1

    def test_expired_budget_is_409(self, client_session, flow):
        _, budget = flow.waiting()
        now = timezone.now()
        Budget.objects.filter(pk=budget.pk).update(
            date_creation=now - timedelta(days=10),
            date_validity=now - timedelta(days=1),
        )

        response = client_session.post(f"/api/budgets/{budget.pk}/approve/")

        assert response.status_code == 409
        assert "fora da validade" in response.json()["detail"]

    def test_reject_returns_attendance_to_requested(self, client_session, flow):
        attendance, budget = flow.waiting()

        response = client_session.post(f"/api/budgets/{budget.pk}/reject/")

        assert response.status_code == 200
        assert response.json()["status_budget"] == "rejected"
        assert response.json()["attendance"]["status_attendance"] == "requested"

    def test_unsent_budget_cannot_be_approved_or_rejected(self, client_session, flow):
        _, budget = flow.budgeted()
        assert (
            client_session.post(f"/api/budgets/{budget.pk}/approve/").status_code == 409
        )
        assert (
            client_session.post(f"/api/budgets/{budget.pk}/reject/").status_code == 409
        )

    def test_second_answer_is_409(self, client_session, flow):
        _, budget = flow.waiting()
        client_session.post(f"/api/budgets/{budget.pk}/approve/")
        assert (
            client_session.post(f"/api/budgets/{budget.pk}/reject/").status_code == 409
        )

    def test_budget_of_another_client_is_404(self, client_session):
        budget = BudgetFactory()
        assert (
            client_session.post(f"/api/budgets/{budget.pk}/approve/").status_code == 404
        )
        assert (
            client_session.post(f"/api/budgets/{budget.pk}/reject/").status_code == 404
        )

    def test_workshop_cannot_answer(self, ready_workshop_session, flow):
        _, budget = flow.waiting()
        assert (
            ready_workshop_session.post(
                f"/api/budgets/{budget.pk}/approve/"
            ).status_code
            == 403
        )
