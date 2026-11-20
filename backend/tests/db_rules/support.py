"""Apoio da suíte das regras do banco (BE-079).

* `violates(sqlstate, mensagem)`: a instrução dentro do bloco precisa falhar no banco
  com esse SQLSTATE e mensagem (a transação do teste continua utilizável: savepoint).
* `covers(objeto, positive=..., negative=...)`: registra que o teste cobre um trigger ou
  função do `init.sql`; `test_coverage.py` exige ≥ 1 positivo e ≥ 1 negativo de cada.
* `attendance_at(status)`: leva um atendimento ao estado pelos caminhos que os
  triggers permitem (o banco valida cada passo).
"""

from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from apps.attendances.models import Attendance, Budget, BudgetItem
from apps.core.db_errors import db_error_details
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    ProductFactory,
    WorkshopServiceFactory,
)
from django.db import DatabaseError, connection, transaction

CHECK = "23514"
UNIQUE = "23505"
FOREIGN_KEY = "23503"
RAISE = "P0001"

STATUSES = (
    "requested",
    "budgeted",
    "waiting_approval",
    "approved",
    "in_progress",
    "completed",
    "delivered",
    "canceled",
)
ALLOWED_TRANSITIONS = {
    ("requested", "budgeted"),
    ("requested", "canceled"),
    ("budgeted", "waiting_approval"),
    ("budgeted", "requested"),
    ("budgeted", "canceled"),
    ("waiting_approval", "approved"),
    ("waiting_approval", "requested"),
    ("waiting_approval", "canceled"),
    ("approved", "in_progress"),
    ("approved", "canceled"),
    ("in_progress", "completed"),
    ("in_progress", "canceled"),
    ("completed", "delivered"),
    ("completed", "in_progress"),
}

COVERAGE: dict[str, dict[str, set]] = {}


def covers(*names, positive=False, negative=False):
    """Registra o teste como prova positiva e/ou negativa de cada trigger/função."""

    def decorate(test):
        for name in names:
            entry = COVERAGE.setdefault(name, {"positive": set(), "negative": set()})
            if positive:
                entry["positive"].add(test.__qualname__)
            if negative:
                entry["negative"].add(test.__qualname__)
        return test

    return decorate


@contextmanager
def violates(sqlstate, message=None):
    with pytest.raises(DatabaseError) as info:
        with transaction.atomic():
            yield info
    state, _, primary = db_error_details(info.value)
    assert state == sqlstate, f"SQLSTATE {state} (esperado {sqlstate}): {primary}"
    if message is not None:
        assert message in (primary or ""), primary


def scalar(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def set_status(attendance, status):
    """UPDATE do status (os triggers da linha disparam)."""
    Attendance.objects.filter(pk=attendance.pk).update(status_attendance=status)
    attendance.refresh_from_db()


def set_budget(budget, status):
    Budget.objects.filter(pk=budget.pk).update(status_budget=status)
    budget.refresh_from_db()


def set_execution(item, status):
    BudgetItem.objects.filter(pk=item.pk).update(execution_status=status)
    item.refresh_from_db()


@dataclass
class Case:
    attendance: Attendance
    budget: Budget | None = None
    items: list = field(default_factory=list)

    def refresh(self):
        self.attendance.refresh_from_db()
        if self.budget is not None:
            self.budget.refresh_from_db()
        for item in self.items:
            item.refresh_from_db()
        return self


def attendance_at(status, *, history_items=False, **attendance_fields):
    """Atendimento no `status`, com orçamento e itens quando o estado exige.

    `history_items=True` usa um item de serviço e uma peça (geram histórico na entrega);
    senão, um item de mão de obra (não precisa de decisão de execução).
    """
    attendance = AttendanceFactory(**attendance_fields)
    case = Case(attendance)
    if status == "requested":
        return case
    if status == "canceled":
        set_status(attendance, "canceled")
        return case

    budget = BudgetFactory(attendance=attendance)  # trigger: requested → budgeted
    case.budget = budget
    if history_items:
        service = WorkshopServiceFactory(workshop=attendance.workshop)
        service_item = BudgetItemFactory(
            budget=budget,
            item_type="service",
            workshop_service=service,
            description="Troca de óleo",
            unit_price="100.00",
        )
        product = ProductFactory(workshop=attendance.workshop)
        part_item = BudgetItemFactory(
            budget=budget,
            item_type="product",
            product=product,
            service_item=service_item,
            description="Filtro",
            quantity="2",
            unit_price="30.00",
        )
        case.items = [service_item, part_item]
    else:
        case.items = [BudgetItemFactory(budget=budget)]
    if status == "budgeted":
        return case.refresh()

    set_status(attendance, "waiting_approval")
    if status == "waiting_approval":
        return case.refresh()

    set_budget(budget, "approved")  # trigger: waiting_approval → approved
    if status == "approved":
        return case.refresh()

    set_status(attendance, "in_progress")
    if status == "in_progress":
        return case.refresh()

    for item in case.items:
        if item.item_type in ("service", "product"):
            set_execution(item, "executed")
    set_status(attendance, "completed")
    if status == "completed":
        return case.refresh()

    set_status(attendance, "delivered")
    assert status == "delivered", status
    return case.refresh()
