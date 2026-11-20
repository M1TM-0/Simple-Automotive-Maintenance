"""BUDGET e BUDGET_ITEM — ciclo comercial, sincronização com o atendimento, total e
proteção do snapshot dos itens (init.sql 9.5 e 9.6; RB-08…RB-14)."""

from datetime import timedelta

import pytest
from apps.attendances.models import Budget, BudgetItem
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    make_review,
)
from django.utils import timezone

from .support import (
    CHECK,
    FOREIGN_KEY,
    attendance_at,
    covers,
    scalar,
    set_budget,
    set_execution,
    set_status,
    violates,
)

pytestmark = [pytest.mark.db_rules, pytest.mark.django_db]


def _expired_pending(attendance=None, days=1):
    """Orçamento pendente já vencido (data de criação no passado)."""
    now = timezone.now()
    budget = BudgetFactory(
        attendance=attendance or AttendanceFactory(),
        date_creation=now - timedelta(days=10),
        date_validity=now - timedelta(days=days),
    )
    BudgetItemFactory(budget=budget)
    return budget


class TestBudgetBeforeWrite:
    """`trg_budget_before_write`."""

    @covers("trg_budget_before_write", positive=True)
    def test_insert_fills_workshop_and_starts_pending_with_zero_total(self):
        attendance = AttendanceFactory()
        budget = Budget.objects.create(attendance=attendance)
        budget.refresh_from_db()
        assert (budget.workshop_id, budget.status_budget, str(budget.total_price)) == (
            attendance.workshop_id,
            "pending",
            "0.00",
        )

    @covers("trg_budget_before_write", negative=True)
    @pytest.mark.parametrize(
        "status",
        [
            "waiting_approval",
            "approved",
            "in_progress",
            "completed",
            "delivered",
            "canceled",
        ],
    )
    def test_insert_refused_when_attendance_is_past_budgeting(self, status):
        case = attendance_at(status)
        with violates(
            CHECK,
            f"Não é possível criar orçamento para atendimento com status {status}.",
        ):
            BudgetFactory(attendance=case.attendance)

    @covers("trg_budget_before_write", negative=True)
    def test_insert_must_be_pending(self):
        with violates(CHECK, "Um orçamento deve ser criado com status pending."):
            BudgetFactory(status_budget="approved")

    @covers("trg_budget_before_write", negative=True)
    def test_insert_total_comes_from_items(self):
        with violates(
            CHECK, "total_price é calculado a partir dos itens do orçamento."
        ):
            BudgetFactory(total_price="10.00")

    @covers("trg_budget_before_write", negative=True)
    def test_insert_for_missing_attendance(self):
        with violates(FOREIGN_KEY, "O atendimento 0 não existe."):
            scalar(
                "INSERT INTO budget (id_attendance, id_workshop) VALUES (0, 0) RETURNING id_budget"
            )

    @covers("trg_budget_before_write", negative=True)
    def test_attendance_and_workshop_are_immutable(self):
        budget = BudgetFactory()
        other = AttendanceFactory(workshop=budget.workshop)
        with violates(
            CHECK, "O atendimento/oficina de um orçamento não pode ser alterado."
        ):
            Budget.objects.filter(pk=budget.pk).update(attendance=other)

    @covers("trg_budget_before_write", negative=True)
    def test_total_cannot_be_written_by_hand(self):
        budget = BudgetItemFactory().budget
        with violates(
            CHECK, "total_price é calculado automaticamente a partir dos itens."
        ):
            Budget.objects.filter(pk=budget.pk).update(total_price="1.00")

    @covers("trg_budget_before_write", positive=True)
    def test_validity_changes_while_pending(self):
        budget = BudgetFactory()
        new_validity = timezone.now() + timedelta(days=20)
        Budget.objects.filter(pk=budget.pk).update(date_validity=new_validity)
        budget.refresh_from_db()
        assert budget.date_validity == new_validity

    @covers("trg_budget_before_write", negative=True)
    def test_validity_is_frozen_after_the_answer(self):
        case = attendance_at("approved")
        with violates(
            CHECK,
            "A validade só pode ser alterada em orçamento que permanece pendente.",
        ):
            Budget.objects.filter(pk=case.budget.pk).update(
                date_validity=timezone.now() + timedelta(days=30)
            )

    @covers("trg_budget_before_write", negative=True)
    def test_cannot_expire_early_by_shortening_validity_in_the_same_update(self):
        budget = BudgetFactory()
        with violates(
            CHECK,
            "A validade só pode ser alterada em orçamento que permanece pendente.",
        ):
            Budget.objects.filter(pk=budget.pk).update(
                status_budget="expired",
                date_validity=budget.date_creation + timedelta(seconds=1),
            )

    @covers("trg_budget_before_write", negative=True)
    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ("rejected", "approved"),
            ("rejected", "pending"),
            ("expired", "pending"),
            ("cancelled", "pending"),
            ("approved", "rejected"),
            ("approved", "pending"),
        ],
    )
    def test_forbidden_budget_transitions(self, old, new):
        case = attendance_at("waiting_approval")
        if old == "approved":
            set_budget(case.budget, "approved")
        elif old == "expired":
            case = attendance_at("requested")
            case.budget = _expired_pending(case.attendance)
            set_budget(case.budget, "expired")
        else:
            set_budget(case.budget, old)
        with violates(CHECK, f"Transição de orçamento inválida: {old} -> {new}."):
            Budget.objects.filter(pk=case.budget.pk).update(status_budget=new)

    @covers("trg_budget_before_write", negative=True)
    def test_approval_requires_waiting_approval(self):
        case = attendance_at("budgeted")
        with violates(
            CHECK,
            "O orçamento só pode ser aprovado com o atendimento em waiting_approval (atual: budgeted).",
        ):
            set_budget(case.budget, "approved")

    @covers("trg_budget_before_write", negative=True)
    def test_approval_requires_validity(self):
        attendance = AttendanceFactory()
        budget = _expired_pending(attendance)
        set_status(attendance, "waiting_approval")
        with violates(CHECK, "O orçamento está fora da validade"):
            set_budget(budget, "approved")

    @covers("trg_budget_before_write", negative=True)
    def test_approval_requires_items(self):
        case = attendance_at("waiting_approval")
        # Remove o único item enquanto pendente; o atendimento continua aguardando.
        BudgetItem.objects.filter(budget=case.budget).delete()
        with violates(CHECK, "Um orçamento sem itens não pode ser aprovado."):
            set_budget(case.budget, "approved")

    @covers("trg_budget_before_write", positive=True)
    def test_approval_and_rejection_stamp_the_response_date(self):
        approved = attendance_at("approved").budget
        case = attendance_at("waiting_approval")
        set_budget(case.budget, "rejected")
        assert (
            approved.date_response is not None and case.budget.date_response is not None
        )

    @covers("trg_budget_before_write", negative=True)
    def test_cannot_expire_within_validity(self):
        budget = BudgetFactory()
        with violates(CHECK, "O orçamento ainda está dentro da validade"):
            set_budget(budget, "expired")

    @covers("trg_budget_before_write", negative=True)
    def test_approved_budget_is_only_cancelled_with_the_attendance(self):
        case = attendance_at("approved")
        with violates(
            CHECK, "Um orçamento aprovado só é cancelado junto com o atendimento."
        ):
            set_budget(case.budget, "cancelled")

    @covers("trg_budget_before_write", negative=True)
    def test_reviewed_budget_cannot_be_cancelled(self):
        """A avaliação exige atendimento entregue, que é final: a regra "orçamento avaliado
        não é cancelado" é defensiva e quem barra antes é a do atendimento cancelado."""
        case = attendance_at("delivered")
        make_review(case.budget)
        with violates(
            CHECK, "Um orçamento aprovado só é cancelado junto com o atendimento."
        ):
            set_budget(case.budget, "cancelled")


class TestBudgetAfterWrite:
    """`trg_budget_after_write`: sincroniza o atendimento."""

    @covers("trg_budget_after_write", positive=True)
    def test_insert_moves_requested_to_budgeted(self):
        attendance = AttendanceFactory()
        BudgetFactory(attendance=attendance)
        attendance.refresh_from_db()
        assert attendance.status_attendance == "budgeted"

    @covers("trg_budget_after_write", positive=True)
    def test_approval_approves_the_attendance(self):
        case = attendance_at("waiting_approval")
        set_budget(case.budget, "approved")
        case.attendance.refresh_from_db()
        assert case.attendance.status_attendance == "approved"

    @covers("trg_budget_after_write", positive=True)
    @pytest.mark.parametrize(
        ("source", "status"),
        [
            ("waiting_approval", "rejected"),
            ("budgeted", "cancelled"),
            ("waiting_approval", "cancelled"),
        ],
    )
    def test_rejection_or_cancellation_returns_to_requested(self, source, status):
        case = attendance_at(source)
        set_budget(case.budget, status)
        case.attendance.refresh_from_db()
        assert case.attendance.status_attendance == "requested"

    @covers("trg_budget_after_write", negative=True)
    def test_observation_change_does_not_touch_the_attendance(self):
        case = attendance_at("waiting_approval")
        Budget.objects.filter(pk=case.budget.pk).update(observations="Revisado")
        case.attendance.refresh_from_db()
        assert case.attendance.status_attendance == "waiting_approval"

    @covers("trg_budget_after_write", negative=True)
    def test_cancelling_with_the_attendance_does_not_reopen_it(self):
        case = attendance_at("approved")
        set_status(case.attendance, "canceled")
        case.attendance.refresh_from_db()
        assert case.attendance.status_attendance == "canceled"


class TestExpirePendingBudgets:
    """`expire_pending_budgets()`: só o vencido; idempotente."""

    @covers("expire_pending_budgets", positive=True, negative=True)
    def test_only_the_expired_pending_budget_expires(self):
        vencido = attendance_at("requested")
        vencido.budget = _expired_pending(vencido.attendance)
        set_status(vencido.attendance, "waiting_approval")
        vigente = attendance_at("waiting_approval")

        assert scalar("SELECT expire_pending_budgets()") == 1

        vencido.refresh()
        vigente.refresh()
        assert (vencido.budget.status_budget, vencido.attendance.status_attendance) == (
            "expired",
            "requested",
        )
        assert (vigente.budget.status_budget, vigente.attendance.status_attendance) == (
            "pending",
            "waiting_approval",
        )
        assert scalar("SELECT expire_pending_budgets()") == 0

    @covers("expire_pending_budgets", negative=True)
    def test_answered_budgets_are_never_touched(self):
        case = attendance_at("approved")
        assert scalar("SELECT expire_pending_budgets()") == 0
        case.refresh()
        assert case.budget.status_budget == "approved"


class TestBudgetItemGuard:
    """`trg_budget_item_guard`."""

    @covers("trg_budget_item_guard", positive=True)
    def test_insert_fills_the_workshop(self):
        budget = BudgetFactory()
        item = BudgetItem.objects.create(
            budget=budget, item_type="other", description="Taxa", unit_price="5.00"
        )
        item.refresh_from_db()
        assert item.workshop_id == budget.workshop_id

    @covers("trg_budget_item_guard", negative=True)
    def test_insert_only_into_pending_budget(self):
        case = attendance_at("approved")
        with violates(
            CHECK,
            "Itens só podem ser incluídos em orçamento pendente (status: approved).",
        ):
            BudgetItemFactory(budget=case.budget)

    @covers("trg_budget_item_guard", negative=True)
    def test_new_item_starts_pending(self):
        budget = BudgetFactory()
        with violates(CHECK, "Um item novo deve iniciar com execution_status pending."):
            BudgetItemFactory(budget=budget, execution_status="not_executed")

    @covers("trg_budget_item_guard", negative=True)
    def test_item_cannot_move_to_another_budget(self):
        item = BudgetItemFactory()
        other = BudgetFactory(attendance=AttendanceFactory(workshop=item.workshop))
        with violates(CHECK, "Um item não pode ser movido para outro orçamento."):
            BudgetItem.objects.filter(pk=item.pk).update(budget=other)

    @covers("trg_budget_item_guard", positive=True)
    def test_commercial_data_changes_while_pending(self):
        item = BudgetItemFactory()
        BudgetItem.objects.filter(pk=item.pk).update(unit_price="90.00")
        item.refresh_from_db()
        assert str(item.unit_price) == "90.00"

    @covers("trg_budget_item_guard", negative=True)
    def test_commercial_data_is_frozen_after_approval(self):
        case = attendance_at("approved")
        with violates(
            CHECK,
            "Os dados comerciais do item são imutáveis após o envio do orçamento (status: approved).",
        ):
            BudgetItem.objects.filter(pk=case.items[0].pk).update(unit_price="1.00")

    @covers("trg_budget_item_guard", positive=True)
    def test_execution_during_in_progress_stamps_executed_at(self):
        case = attendance_at("in_progress", history_items=True)
        set_execution(case.items[0], "executed")
        assert case.items[0].executed_at is not None
        set_execution(case.items[0], "not_executed")
        assert case.items[0].executed_at is None

    @covers("trg_budget_item_guard", negative=True)
    @pytest.mark.parametrize(
        "status", ["waiting_approval", "approved", "completed", "delivered"]
    )
    def test_execution_only_while_in_progress(self, status):
        case = attendance_at(status, history_items=True)
        with violates(
            CHECK,
            "A execução só pode ser registrada em orçamento aprovado com o atendimento em in_progress",
        ):
            set_execution(
                case.items[0],
                "not_executed" if status in ("completed", "delivered") else "executed",
            )

    @covers("trg_budget_item_guard", positive=True)
    def test_delete_while_pending(self):
        item = BudgetItemFactory()
        BudgetItem.objects.filter(pk=item.pk).delete()
        assert not BudgetItem.objects.filter(pk=item.pk).exists()

    @covers("trg_budget_item_guard", negative=True)
    def test_delete_after_approval_is_refused(self):
        case = attendance_at("approved")
        with violates(
            CHECK,
            "Itens só podem ser removidos de orçamento pendente (status: approved).",
        ):
            BudgetItem.objects.filter(pk=case.items[0].pk).delete()


class TestBudgetTotal:
    """`trg_budget_item_recalc_total`: total = soma dos subtotais."""

    @covers("trg_budget_item_recalc_total", positive=True)
    def test_total_follows_insert_update_and_delete(self):
        budget = BudgetFactory()
        first = BudgetItemFactory(budget=budget, quantity="2.5", unit_price="10.01")
        BudgetItemFactory(budget=budget, unit_price="5.00")
        budget.refresh_from_db()
        assert str(budget.total_price) == "30.03"  # ROUND(2,5 × 10,01) = 25,03 + 5,00

        BudgetItem.objects.filter(pk=first.pk).update(quantity="1")
        budget.refresh_from_db()
        assert str(budget.total_price) == "15.01"

        BudgetItem.objects.filter(pk=first.pk).delete()
        budget.refresh_from_db()
        assert str(budget.total_price) == "5.00"

    @covers("trg_budget_item_recalc_total", negative=True)
    def test_description_change_does_not_recalculate(self):
        item = BudgetItemFactory(unit_price="80.00")
        BudgetItem.objects.filter(pk=item.pk).update(description="Outra descrição")
        item.budget.refresh_from_db()
        assert str(item.budget.total_price) == "80.00"
