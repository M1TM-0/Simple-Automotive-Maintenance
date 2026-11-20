"""ATTENDANCE — máquina de estados, vínculo com o orçamento e geração do histórico
(init.sql 9.3; RB-03…RB-08)."""

import itertools

import pytest
from apps.attendances.models import Attendance, Budget
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
)
from apps.vehicles.models import RegisterMaintenance, RegisterMaintenancePart

from .support import (
    ALLOWED_TRANSITIONS,
    CHECK,
    STATUSES,
    attendance_at,
    covers,
    scalar,
    set_budget,
    set_execution,
    set_status,
    violates,
)

pytestmark = [pytest.mark.db_rules, pytest.mark.django_db]


class TestTransitionFunction:
    """`attendance_transition_allowed(old, new)`: as 64 combinações."""

    @covers("attendance_transition_allowed", positive=True, negative=True)
    @pytest.mark.parametrize(
        ("old", "new"), list(itertools.product(STATUSES, STATUSES))
    )
    def test_every_pair(self, old, new):
        allowed = scalar("SELECT attendance_transition_allowed(%s, %s)", [old, new])
        assert allowed is ((old, new) in ALLOWED_TRANSITIONS)

    def test_fourteen_transitions_and_two_final_states(self):
        assert len(ALLOWED_TRANSITIONS) == 14
        sources = {old for old, _ in ALLOWED_TRANSITIONS}
        assert set(STATUSES) - sources == {"delivered", "canceled"}


def _requested_to_budgeted(case):
    BudgetFactory(
        attendance=case.attendance
    )  # o trigger AFTER INSERT do orçamento move


def _waiting_to_approved(case):
    set_budget(case.budget, "approved")  # aprovação do orçamento aprova o atendimento


def _waiting_to_requested(case):
    set_budget(case.budget, "rejected")


def _budgeted_to_requested(case):
    set_budget(case.budget, "cancelled")


def _in_progress_to_completed(case):
    for item in case.items:
        if item.item_type in ("service", "product"):
            set_execution(item, "executed")
    set_status(case.attendance, "completed")


PERFORM = {
    ("requested", "budgeted"): _requested_to_budgeted,
    ("waiting_approval", "approved"): _waiting_to_approved,
    ("waiting_approval", "requested"): _waiting_to_requested,
    ("budgeted", "requested"): _budgeted_to_requested,
    ("in_progress", "completed"): _in_progress_to_completed,
}


class TestAttendanceTrigger:
    """`trg_attendance_before_write` e `trg_attendance_after_status`."""

    @covers("trg_attendance_before_write", positive=True)
    @pytest.mark.parametrize(("old", "new"), sorted(ALLOWED_TRANSITIONS))
    def test_allowed_transition(self, old, new):
        case = attendance_at(old, history_items=True)
        perform = PERFORM.get((old, new), lambda c: set_status(c.attendance, new))

        perform(case)

        case.attendance.refresh_from_db()
        assert case.attendance.status_attendance == new

    @covers("trg_attendance_before_write", negative=True)
    @pytest.mark.parametrize(
        ("old", "new"),
        [
            (o, n)
            for o, n in itertools.product(STATUSES, STATUSES)
            if o != n and (o, n) not in ALLOWED_TRANSITIONS
        ],
    )
    def test_forbidden_transition(self, old, new):
        case = attendance_at(old)
        with violates(CHECK, f"Transição de atendimento inválida: {old} -> {new}."):
            Attendance.objects.filter(pk=case.attendance.pk).update(
                status_attendance=new
            )

    @covers("trg_attendance_before_write", negative=True)
    def test_must_be_created_as_requested(self):
        with violates(
            CHECK,
            "Um atendimento deve ser criado com status requested (recebido: approved).",
        ):
            AttendanceFactory(status_attendance="approved")

    @covers("trg_attendance_before_write", positive=True)
    def test_same_status_update_is_a_no_op(self):
        case = attendance_at("approved")
        set_status(case.attendance, "approved")
        assert case.attendance.status_attendance == "approved"

    @covers("trg_attendance_before_write", negative=True)
    def test_budgeted_requires_a_pending_budget(self):
        attendance = AttendanceFactory()
        with violates(
            CHECK, f"O atendimento {attendance.pk} não possui orçamento pendente."
        ):
            set_status(attendance, "budgeted")

    @covers("trg_attendance_before_write", negative=True)
    def test_waiting_approval_requires_items(self):
        attendance = AttendanceFactory()
        BudgetFactory(attendance=attendance)
        with violates(
            CHECK,
            f"O orçamento pendente do atendimento {attendance.pk} não possui itens.",
        ):
            set_status(attendance, "waiting_approval")

    @covers("trg_attendance_before_write", negative=True)
    def test_approved_requires_an_approved_budget(self):
        case = attendance_at("waiting_approval")
        with violates(
            CHECK, f"O atendimento {case.attendance.pk} não possui orçamento aprovado."
        ):
            set_status(case.attendance, "approved")

    @covers("trg_attendance_before_write", negative=True)
    def test_completion_requires_every_service_and_part_decided(self):
        case = attendance_at("in_progress", history_items=True)
        set_execution(case.items[0], "executed")  # a peça continua pendente
        with violates(
            CHECK,
            "Existem serviços ou produtos do orçamento ainda sem situação de execução.",
        ):
            set_status(case.attendance, "completed")

    @covers("trg_attendance_before_write", positive=True)
    def test_labor_items_do_not_need_a_decision(self):
        case = attendance_at("in_progress")  # só mão de obra
        set_status(case.attendance, "completed")
        assert case.attendance.status_attendance == "completed"

    @covers("trg_attendance_after_status", positive=True)
    @pytest.mark.parametrize(
        "source", ["budgeted", "waiting_approval", "approved", "in_progress"]
    )
    def test_cancel_cancels_open_and_approved_budgets(self, source):
        case = attendance_at(source)
        set_status(case.attendance, "canceled")
        case.budget.refresh_from_db()
        assert case.budget.status_budget == "cancelled"

    @covers("trg_attendance_after_status", negative=True)
    def test_cancel_keeps_rejected_budgets_and_creates_no_history(self):
        case = attendance_at("waiting_approval", history_items=True)
        set_budget(case.budget, "rejected")
        set_status(case.attendance, "canceled")
        case.budget.refresh_from_db()
        assert case.budget.status_budget == "rejected"
        assert not RegisterMaintenance.objects.filter(
            attendance=case.attendance
        ).exists()

    @covers("trg_attendance_after_status", positive=True)
    def test_delivery_generates_history_of_executed_items_only(self):
        case = attendance_at("in_progress", history_items=True)
        set_execution(case.items[0], "executed")
        set_execution(case.items[1], "not_executed")
        set_status(case.attendance, "completed")
        set_status(case.attendance, "delivered")

        services = RegisterMaintenance.objects.filter(attendance=case.attendance)
        parts = RegisterMaintenancePart.objects.filter(attendance=case.attendance)
        assert [r.budget_item_id for r in services] == [case.items[0].pk]
        assert not parts.exists(), "peça não utilizada não entra no histórico"

    @covers("trg_attendance_after_status", negative=True)
    def test_reopening_generates_nothing(self):
        case = attendance_at("completed", history_items=True)
        set_status(case.attendance, "in_progress")
        assert not RegisterMaintenance.objects.filter(
            attendance=case.attendance
        ).exists()


class TestRegisterAttendanceHistory:
    """`register_attendance_history(id)`: idempotente e só para entregue."""

    @covers("register_attendance_history", positive=True)
    def test_second_call_returns_zero(self):
        case = attendance_at("delivered", history_items=True)
        assert (
            RegisterMaintenance.objects.filter(attendance=case.attendance).count() == 1
        )
        assert (
            RegisterMaintenancePart.objects.filter(attendance=case.attendance).count()
            == 1
        )

        assert (
            scalar("SELECT register_attendance_history(%s)", [case.attendance.pk]) == 0
        )
        assert (
            RegisterMaintenance.objects.filter(attendance=case.attendance).count() == 1
        )

    @covers("register_attendance_history", positive=True)
    def test_copies_snapshot_of_the_item(self):
        case = attendance_at("delivered", history_items=True)
        part = RegisterMaintenancePart.objects.get(attendance=case.attendance)
        service = RegisterMaintenance.objects.get(attendance=case.attendance)
        assert (part.description, str(part.quantity), str(part.unit_price)) == (
            "Filtro",
            "2.000",
            "30.00",
        )
        assert service.service_name == "Troca de óleo"
        assert service.mileage_km == case.attendance.mileage_km

    @covers("register_attendance_history", negative=True)
    @pytest.mark.parametrize("status", ["completed", "canceled", "requested"])
    def test_refused_unless_delivered(self, status):
        case = attendance_at(status)
        with violates(
            CHECK,
            f"O histórico só é gerado para atendimento entregue (status atual: {status}).",
        ):
            scalar("SELECT register_attendance_history(%s)", [case.attendance.pk])

    @covers("register_attendance_history", negative=True)
    def test_unknown_attendance(self):
        with violates("P0001", "O atendimento 0 não existe."):
            scalar("SELECT register_attendance_history(0)")

    def test_only_the_approved_budget_counts(self):
        """Um orçamento recusado antes do aprovado nunca gera histórico."""
        attendance = AttendanceFactory()
        first = BudgetFactory(attendance=attendance)
        BudgetItemFactory(budget=first)
        set_status(attendance, "waiting_approval")
        set_budget(first, "rejected")
        attendance.refresh_from_db()
        assert attendance.status_attendance == "requested"
        assert (
            Budget.objects.filter(
                attendance=attendance, status_budget="rejected"
            ).count()
            == 1
        )
