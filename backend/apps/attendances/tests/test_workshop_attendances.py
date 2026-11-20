"""BE-049…BE-055: atendimentos, transições, orçamento, itens, envio, execução e clientes."""

from datetime import timedelta

import pytest
from apps.attendances.models import Attendance, Budget, BudgetItem
from apps.attendances.tests.conftest import move
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    ClientFactory,
    PagWorkshopFactory,
    ProductFactory,
    VehicleFactory,
    WorkshopServiceFactory,
    make_ready_workshop,
)
from apps.vehicles.models import RegisterMaintenance, RegisterMaintenancePart, Vehicle
from django.db import connection
from django.utils import timezone

W = "/api/workshop/"


# ------------------------------------------------------------------ BE-049


@pytest.mark.django_db
class TestWorkshopAttendances:
    def test_board_is_isolated_and_filterable(self, ready_workshop_session, flow):
        requested = flow.requested()
        budgeted, _ = flow.budgeted()
        flow.delivered()
        AttendanceFactory(workshop=make_ready_workshop())

        rows = ready_workshop_session.get(
            f"{W}attendances/", {"status": "requested,budgeted"}
        ).json()["results"]

        assert sorted(row["id"] for row in rows) == sorted([requested.pk, budgeted.pk])
        row = next(r for r in rows if r["id"] == budgeted.pk)
        assert set(row["client"]) == {"id", "name"}
        assert row["total_price"] == "160.00"
        assert ready_workshop_session.get(f"{W}attendances/").json()["count"] == 3

    def test_detail_of_another_workshop_is_404(self, ready_workshop_session):
        other = AttendanceFactory(workshop=make_ready_workshop())
        assert (
            ready_workshop_session.get(f"{W}attendances/{other.pk}/").status_code == 404
        )
        assert (
            ready_workshop_session.patch(
                f"{W}attendances/{other.pk}/", {}, format="json"
            ).status_code
            == 404
        )

    def test_detail_has_client_phone_vehicle_and_budgets(
        self, ready_workshop_session, flow, client_account
    ):
        client_account.__class__.objects.filter(pk=client_account.pk).update(
            phone_number="86 9999-0000"
        )
        attendance, budget = flow.waiting()

        body = ready_workshop_session.get(f"{W}attendances/{attendance.pk}/").json()

        assert body["client"] == {
            "id": client_account.pk,
            "name": client_account.name,
            "phone_number": "86 9999-0000",
        }
        assert body["vehicle"]["plate"] == attendance.vehicle.plate
        assert body["budgets"][0]["id"] == budget.pk
        assert "email" not in body["client"]

    def test_patch_ignores_status_and_keeps_client_observations(
        self, ready_workshop_session, flow
    ):
        attendance = flow.requested(observations="Pedido do cliente")

        response = ready_workshop_session.patch(
            f"{W}attendances/{attendance.pk}/",
            {
                "status_attendance": "delivered",
                "status": "delivered",
                "mileage_km": 70000,
                "observations": "Pastilhas gastas",
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        attendance.refresh_from_db()
        assert attendance.status_attendance == "requested"
        assert (attendance.mileage_km, attendance.technical_notes) == (
            70000,
            "Pastilhas gastas",
        )
        assert attendance.observations == "Pedido do cliente"
        assert response.json()["technical_notes"] == "Pastilhas gastas"

    @pytest.mark.parametrize("state", ["delivered", "canceled"])
    def test_patch_final_attendance_is_409(self, ready_workshop_session, flow, state):
        if state == "canceled":
            attendance = flow.requested()
            Attendance.objects.filter(pk=attendance.pk).update(
                status_attendance="canceled"
            )
        else:
            attendance, _ = flow.delivered()
        response = ready_workshop_session.patch(
            f"{W}attendances/{attendance.pk}/", {"mileage_km": 1}, format="json"
        )
        assert response.status_code == 409

    def test_setup_incomplete_workshop_gets_403(self, workshop_session):
        """BE-028: rota administrativa real bloqueada até o cadastro oficial."""
        response = workshop_session.get(f"{W}attendances/")
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Conclua o cadastro da oficina para acessar este recurso."
        }

    def test_access_matrix(self, api_client, client_session):
        assert api_client.get(f"{W}attendances/").status_code == 401
        assert client_session.get(f"{W}attendances/").status_code == 403


# ------------------------------------------------------------------ BE-050


def transition(api, attendance, status):
    return api.post(
        f"{W}attendances/{attendance.pk}/transition/", {"status": status}, format="json"
    )


@pytest.mark.django_db
class TestTransitions:
    @pytest.mark.parametrize(
        ("state", "target"),
        [
            ("approved", "in_progress"),
            ("completed", "in_progress"),  # reabertura
            ("completed", "delivered"),
            ("requested", "canceled"),
            ("budgeted", "canceled"),
            ("waiting", "canceled"),
            ("approved", "canceled"),
            ("in_progress", "canceled"),
        ],
    )
    def test_allowed(self, ready_workshop_session, flow, state, target):
        attendance, _ = flow.at(state)
        response = transition(ready_workshop_session, attendance, target)
        assert response.status_code == 200, response.json()
        assert response.json()["status_attendance"] == target

    def test_in_progress_to_completed_after_execution(
        self, ready_workshop_session, flow
    ):
        attendance, budget = flow.in_progress()
        BudgetItem.objects.filter(budget=budget).update(execution_status="not_executed")
        assert (
            transition(ready_workshop_session, attendance, "completed").status_code
            == 200
        )

    @pytest.mark.parametrize(
        ("state", "target"),
        [
            ("requested", "in_progress"),
            ("budgeted", "completed"),
            ("waiting", "in_progress"),
            ("approved", "completed"),
            ("approved", "delivered"),
            ("in_progress", "delivered"),
            ("completed", "canceled"),
            ("delivered", "in_progress"),
            ("delivered", "canceled"),
        ],
    )
    def test_forbidden_are_409_with_db_message(
        self, ready_workshop_session, flow, state, target
    ):
        attendance, _ = flow.at(state)
        response = transition(ready_workshop_session, attendance, target)
        assert response.status_code == 409
        assert response.json()["detail"]

    def test_completion_with_pending_items_is_409(self, ready_workshop_session, flow):
        attendance, _ = flow.in_progress()
        response = transition(ready_workshop_session, attendance, "completed")
        assert response.status_code == 409
        assert "sem situação de execução" in response.json()["detail"]

    @pytest.mark.parametrize(
        "status",
        ["waiting_approval", "budgeted", "approved", "requested", "voando", ""],
    )
    def test_status_outside_whitelist_is_400(
        self, ready_workshop_session, flow, status
    ):
        attendance, _ = flow.waiting()
        response = transition(ready_workshop_session, attendance, status)
        assert response.status_code == 400
        assert "status" in response.json()

    def test_delivery_generates_history_and_updates_mileage(
        self, ready_workshop_session, flow, client_account
    ):
        vehicle = VehicleFactory(client=client_account, mileage_km=50000)
        attendance = flow.requested(vehicle=vehicle, mileage_km=55000)
        attendance, budget = flow.in_progress(attendance)
        # serviço executado entra no histórico; peça não executada não entra
        BudgetItem.objects.filter(pk=budget.service_item.pk).update(
            execution_status="executed", executed_at=timezone.now()
        )
        BudgetItem.objects.filter(pk=budget.part_item.pk).update(
            execution_status="not_executed"
        )
        assert (
            transition(ready_workshop_session, attendance, "completed").status_code
            == 200
        )

        response = transition(ready_workshop_session, attendance, "delivered")

        assert response.status_code == 200
        assert list(
            RegisterMaintenance.objects.filter(attendance=attendance).values_list(
                "service_name", flat=True
            )
        ) == ["Troca de óleo"]
        assert not RegisterMaintenancePart.objects.filter(
            attendance=attendance
        ).exists()
        assert Vehicle.objects.get(pk=vehicle.pk).mileage_km == 55000
        with connection.cursor() as cursor:  # idempotente: 2ª geração não cria nada
            cursor.execute("SELECT register_attendance_history(%s)", [attendance.pk])
            assert cursor.fetchone()[0] == 0

    def test_delivery_never_lowers_vehicle_mileage(
        self, ready_workshop_session, flow, client_account
    ):
        vehicle = VehicleFactory(client=client_account, mileage_km=90000)
        attendance, _ = flow.completed(flow.requested(vehicle=vehicle, mileage_km=10))
        transition(ready_workshop_session, attendance, "delivered")
        assert Vehicle.objects.get(pk=vehicle.pk).mileage_km == 90000

    def test_same_status_twice_is_409(self, ready_workshop_session, flow):
        attendance, _ = flow.approved()
        assert (
            transition(ready_workshop_session, attendance, "in_progress").status_code
            == 200
        )
        assert (
            transition(ready_workshop_session, attendance, "in_progress").status_code
            == 409
        )

    def test_other_workshop_is_404(self, ready_workshop_session):
        other = AttendanceFactory(workshop=make_ready_workshop())
        assert transition(ready_workshop_session, other, "canceled").status_code == 404


# ------------------------------------------------------------------ BE-051


@pytest.mark.django_db
class TestBudgetHeader:
    def test_create_budget_moves_attendance_to_budgeted(
        self, ready_workshop_session, flow
    ):
        attendance = flow.requested()

        response = ready_workshop_session.post(
            f"{W}attendances/{attendance.pk}/budget/",
            {"total_price": "999", "status_budget": "approved"},
            format="json",
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["status_budget"], body["total_price"], body["items"]) == (
            "pending",
            "0.00",
            [],
        )
        validity = timezone.datetime.fromisoformat(body["date_validity"])
        assert (
            timedelta(days=6, hours=23) < validity - timezone.now() <= timedelta(days=7)
        )
        attendance.refresh_from_db()
        assert attendance.status_attendance == "budgeted"

    def test_second_pending_budget_is_409(self, ready_workshop_session, flow):
        attendance, _ = flow.budgeted()
        response = ready_workshop_session.post(
            f"{W}attendances/{attendance.pk}/budget/", {}, format="json"
        )
        assert response.status_code == 409

    def test_budget_for_attendance_in_progress_is_409(
        self, ready_workshop_session, flow
    ):
        attendance, _ = flow.in_progress()
        response = ready_workshop_session.post(
            f"{W}attendances/{attendance.pk}/budget/", {}, format="json"
        )
        assert response.status_code == 409
        assert "Não é possível criar orçamento" in response.json()["detail"]

    def test_patch_validity_and_observations(self, ready_workshop_session, flow):
        _, budget = flow.budgeted()
        future = (timezone.now() + timedelta(days=15)).isoformat()

        response = ready_workshop_session.patch(
            f"{W}budgets/{budget.pk}/",
            {"date_validity": future, "observations": "Peças originais"},
            format="json",
        )

        assert response.status_code == 200, response.json()
        budget.refresh_from_db()
        assert budget.observations == "Peças originais"
        assert budget.date_validity > timezone.now() + timedelta(days=14)

    def test_past_validity_is_400(self, ready_workshop_session, flow):
        _, budget = flow.budgeted()
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        response = ready_workshop_session.patch(
            f"{W}budgets/{budget.pk}/", {"date_validity": past}, format="json"
        )
        assert response.status_code == 400
        assert "date_validity" in response.json()

    @pytest.mark.parametrize("state", ["waiting", "approved"])
    def test_patch_after_sending_is_409(self, ready_workshop_session, flow, state):
        _, budget = flow.at(state)
        response = ready_workshop_session.patch(
            f"{W}budgets/{budget.pk}/", {"observations": "x"}, format="json"
        )
        assert response.status_code == 409

    def test_other_workshop_budget_is_404(self, ready_workshop_session):
        budget = BudgetFactory(
            attendance=AttendanceFactory(workshop=make_ready_workshop())
        )
        assert (
            ready_workshop_session.patch(
                f"{W}budgets/{budget.pk}/", {}, format="json"
            ).status_code
            == 404
        )


# ------------------------------------------------------------------ BE-052


@pytest.mark.django_db
class TestBudgetItems:
    def items_url(self, budget):
        return f"{W}budgets/{budget.pk}/items/"

    def test_service_and_linked_product_total_160(
        self, ready_workshop_session, flow, ready_workshop
    ):
        attendance, budget = flow.budgeted(with_items=False)
        service = WorkshopServiceFactory(workshop=ready_workshop, price_base="100.00")
        product = ProductFactory(workshop=ready_workshop, price="30.00")

        first = ready_workshop_session.post(
            self.items_url(budget),
            {
                "item_type": "service",
                "id_workshop_service": service.pk,
                "quantity": 1,
                "unit_price": 100,
            },
            format="json",
        )
        second = ready_workshop_session.post(
            self.items_url(budget),
            {
                "item_type": "product",
                "id_product": product.pk,
                "id_service_item": first.json()["id"],
                "quantity": "2",
                "unit_price": "30.00",
            },
            format="json",
        )

        assert (first.status_code, second.status_code) == (201, 201), second.json()
        body = second.json()
        assert body["budget"]["total_price"] == "160.00"
        assert (body["subtotal"], body["quantity"], body["description"]) == (
            "60.00",
            "2.000",
            product.name,
        )
        assert body["id_service_item"] == first.json()["id"]
        assert first.json()["description"] == service.service.name
        assert Budget.objects.get(pk=budget.pk).total_price == 160

    def test_catalog_defaults_for_description_and_price(
        self, ready_workshop_session, flow, ready_workshop
    ):
        _, budget = flow.budgeted(with_items=False)
        product = ProductFactory(
            workshop=ready_workshop, name="Pastilha", price="45.90"
        )
        body = ready_workshop_session.post(
            self.items_url(budget),
            {"item_type": "product", "id_product": product.pk},
            format="json",
        ).json()
        assert (body["description"], body["unit_price"], body["quantity"]) == (
            "Pastilha",
            "45.90",
            "1.000",
        )

    @pytest.mark.parametrize("ref", ["id_product", "id_workshop_service"])
    def test_catalog_item_of_another_workshop_is_400(
        self, ready_workshop_session, flow, ref
    ):
        _, budget = flow.budgeted(with_items=False)
        other = make_ready_workshop()
        if ref == "id_product":
            payload = {
                "item_type": "product",
                "id_product": ProductFactory(workshop=other).pk,
            }
        else:
            payload = {
                "item_type": "service",
                "id_workshop_service": WorkshopServiceFactory(workshop=other).pk,
            }
        response = ready_workshop_session.post(
            self.items_url(budget), {**payload, "unit_price": "1"}, format="json"
        )
        assert response.status_code == 400
        assert ref in response.json()

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"quantity": "0.0005"}, "quantity"),
            ({"quantity": "0"}, "quantity"),
            ({"quantity": "0,5"}, "quantity"),
            ({"unit_price": "-1"}, "unit_price"),
            ({"unit_price": "1.999"}, "unit_price"),
            ({"description": "x" * 256}, "description"),
            ({"description": ""}, "description"),
            ({"unit_price": None}, "unit_price"),
            ({"item_type": "gift"}, "item_type"),
            ({"id_product": 1}, "id_product"),
        ],
    )
    def test_invalid_labor_item_is_400(
        self, ready_workshop_session, flow, payload, field
    ):
        _, budget = flow.budgeted(with_items=False)
        data = {
            "item_type": "labor",
            "description": "Mão de obra",
            "quantity": "1",
            "unit_price": "80",
        }
        data.update(payload)
        data = {k: v for k, v in data.items() if v is not None}
        response = ready_workshop_session.post(
            self.items_url(budget), data, format="json"
        )
        assert response.status_code == 400
        assert field in response.json()

    def test_service_item_must_be_a_service_of_this_budget(
        self, ready_workshop_session, flow, ready_workshop
    ):
        _, budget = flow.budgeted(with_items=False)
        labor = BudgetItemFactory(budget=budget)
        product = ProductFactory(workshop=ready_workshop)
        response = ready_workshop_session.post(
            self.items_url(budget),
            {
                "item_type": "product",
                "id_product": product.pk,
                "id_service_item": labor.pk,
            },
            format="json",
        )
        assert response.status_code == 400
        assert "id_service_item" in response.json()

    @pytest.mark.parametrize("state", ["waiting", "approved"])
    def test_items_are_frozen_after_sending(self, ready_workshop_session, flow, state):
        _, budget = flow.at(state)
        add = ready_workshop_session.post(
            self.items_url(budget),
            {"item_type": "labor", "description": "X", "unit_price": "1"},
            format="json",
        )
        edit = ready_workshop_session.patch(
            f"{self.items_url(budget)}{budget.service_item.pk}/",
            {"unit_price": "1"},
            format="json",
        )
        remove = ready_workshop_session.delete(
            f"{self.items_url(budget)}{budget.service_item.pk}/"
        )
        assert (add.status_code, edit.status_code, remove.status_code) == (
            409,
            409,
            409,
        )

    def test_patch_recalculates_total(self, ready_workshop_session, flow):
        _, budget = flow.budgeted()
        response = ready_workshop_session.patch(
            f"{self.items_url(budget)}{budget.part_item.pk}/",
            {"quantity": "3"},
            format="json",
        )
        assert response.status_code == 200, response.json()
        assert response.json()["budget"]["total_price"] == "190.00"
        assert response.json()["id_service_item"] == budget.service_item.pk

    def test_delete_service_removes_linked_parts(self, ready_workshop_session, flow):
        _, budget = flow.budgeted()
        BudgetItemFactory(budget=budget, unit_price="15.00")  # mão de obra fica

        response = ready_workshop_session.delete(
            f"{self.items_url(budget)}{budget.service_item.pk}/"
        )

        assert response.status_code == 204
        assert list(
            BudgetItem.objects.filter(budget=budget).values_list("item_type", flat=True)
        ) == ["labor"]
        assert str(Budget.objects.get(pk=budget.pk).total_price) == "15.00"

    def test_changing_type_of_service_with_parts_is_409(
        self, ready_workshop_session, flow
    ):
        _, budget = flow.budgeted()
        response = ready_workshop_session.patch(
            f"{self.items_url(budget)}{budget.service_item.pk}/",
            {"item_type": "labor", "id_workshop_service": None},
            format="json",
        )
        assert response.status_code == 409

    def test_items_of_another_workshop_are_404(self, ready_workshop_session):
        budget = BudgetFactory(
            attendance=AttendanceFactory(workshop=make_ready_workshop())
        )
        item = BudgetItemFactory(budget=budget)
        assert (
            ready_workshop_session.post(
                self.items_url(budget), {"item_type": "labor"}, format="json"
            ).status_code
            == 404
        )
        assert (
            ready_workshop_session.delete(
                f"{self.items_url(budget)}{item.pk}/"
            ).status_code
            == 404
        )


# ------------------------------------------------------------------ BE-053


@pytest.mark.django_db
class TestSendBudget:
    def test_send_with_items(self, ready_workshop_session, flow):
        attendance, budget = flow.budgeted()
        response = ready_workshop_session.post(f"{W}budgets/{budget.pk}/send/")
        assert response.status_code == 200, response.json()
        assert response.json()["attendance"]["status_attendance"] == "waiting_approval"

    def test_send_without_items_is_409(self, ready_workshop_session, flow):
        _, budget = flow.budgeted(with_items=False)
        response = ready_workshop_session.post(f"{W}budgets/{budget.pk}/send/")
        assert response.status_code == 409
        assert "não possui itens" in response.json()["detail"]

    def test_send_twice_is_409(self, ready_workshop_session, flow):
        _, budget = flow.budgeted()
        ready_workshop_session.post(f"{W}budgets/{budget.pk}/send/")
        assert (
            ready_workshop_session.post(f"{W}budgets/{budget.pk}/send/").status_code
            == 409
        )

    def test_send_expired_is_409(self, ready_workshop_session, flow):
        _, budget = flow.budgeted()
        now = timezone.now()
        Budget.objects.filter(pk=budget.pk).update(
            date_creation=now - timedelta(days=9), date_validity=now - timedelta(days=1)
        )
        assert (
            ready_workshop_session.post(f"{W}budgets/{budget.pk}/send/").status_code
            == 409
        )


# ------------------------------------------------------------------ BE-054


@pytest.mark.django_db
class TestExecution:
    def url(self, budget, item):
        return f"{W}budgets/{budget.pk}/items/{item.pk}/execution/"

    def test_mark_executed_and_back_to_pending(self, ready_workshop_session, flow):
        _, budget = flow.in_progress()

        done = ready_workshop_session.patch(
            self.url(budget, budget.service_item),
            {"execution_status": "executed"},
            format="json",
        )
        assert done.status_code == 200, done.json()
        assert done.json()["executed_at"] is not None

        back = ready_workshop_session.patch(
            self.url(budget, budget.service_item),
            {"execution_status": "pending"},
            format="json",
        )
        assert (back.json()["execution_status"], back.json()["executed_at"]) == (
            "pending",
            None,
        )

    def test_outside_in_progress_is_409(self, ready_workshop_session, flow):
        _, budget = flow.approved()
        response = ready_workshop_session.patch(
            self.url(budget, budget.service_item),
            {"execution_status": "executed"},
            format="json",
        )
        assert response.status_code == 409

    def test_labor_item_is_400(self, ready_workshop_session, flow):
        attendance, budget = flow.budgeted()
        labor = BudgetItemFactory(budget=budget)
        move(attendance, "waiting_approval")
        Budget.objects.filter(pk=budget.pk).update(status_budget="approved")
        move(attendance, "in_progress")
        response = ready_workshop_session.patch(
            self.url(budget, labor), {"execution_status": "executed"}, format="json"
        )
        assert response.status_code == 400

    def test_invalid_value_is_400(self, ready_workshop_session, flow):
        _, budget = flow.in_progress()
        response = ready_workshop_session.patch(
            self.url(budget, budget.part_item),
            {"execution_status": "done"},
            format="json",
        )
        assert response.status_code == 400


# ------------------------------------------------------------------ BE-055


@pytest.mark.django_db
class TestWorkshopClients:
    def test_clients_with_counts_and_attended_vehicles(
        self, ready_workshop_session, flow, client_account
    ):
        car = VehicleFactory(client=client_account)
        for _ in range(3):
            flow.requested(vehicle=car)
        VehicleFactory(client=client_account)  # nunca atendido aqui
        AttendanceFactory(
            client=client_account,
            vehicle=VehicleFactory(client=client_account),
            workshop=make_ready_workshop(),
        )
        AttendanceFactory(workshop=make_ready_workshop())  # cliente de outra oficina

        rows = ready_workshop_session.get(f"{W}clients/").json()["results"]

        assert len(rows) == 1
        row = rows[0]
        assert (row["id"], row["name"], row["attendance_count"]) == (
            client_account.pk,
            client_account.name,
            3,
        )
        assert [v["id"] for v in row["vehicles"]] == [car.pk]
        assert row["last_attendance"]
        assert "email" not in row

    def test_client_vehicles_only_with_this_workshop(
        self, ready_workshop_session, flow, client_account
    ):
        attendance = flow.requested()
        other_shop = AttendanceFactory(
            client=client_account,
            vehicle=attendance.vehicle,
            workshop=make_ready_workshop(),
        )

        rows = ready_workshop_session.get(
            f"{W}clients/{client_account.pk}/vehicles/"
        ).json()["results"]

        assert [v["id"] for v in rows] == [attendance.vehicle_id]
        assert [a["id"] for a in rows[0]["attendances"]] == [attendance.pk]
        assert other_shop.pk not in [a["id"] for a in rows[0]["attendances"]]

    def test_client_without_link_is_404(self, ready_workshop_session):
        stranger = ClientFactory()
        AttendanceFactory(client=stranger, workshop=PagWorkshopFactory().workshop)
        assert (
            ready_workshop_session.get(
                f"{W}clients/{stranger.pk}/vehicles/"
            ).status_code
            == 404
        )

    def test_access_matrix(self, api_client, client_session, workshop_session):
        assert api_client.get(f"{W}clients/").status_code == 401
        assert client_session.get(f"{W}clients/").status_code == 403
        assert workshop_session.get(f"{W}clients/").status_code == 403
