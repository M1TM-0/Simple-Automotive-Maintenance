"""Fixtures para levar atendimentos a cada estado (via ORM; as regras são do banco)."""

import pytest
from apps.attendances.models import AttendanceStatus, BudgetStatus
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    ProductFactory,
    VehicleFactory,
    WorkshopServiceFactory,
)


def move(attendance, status):
    attendance.status_attendance = status
    attendance.save(update_fields=["status_attendance"])


class Flow:
    """Monta um atendimento do cliente na oficina e o conduz pelos estados."""

    def __init__(self, client, workshop):
        self.client = client
        self.workshop = workshop

    def requested(self, **kwargs):
        vehicle = kwargs.pop("vehicle", None) or VehicleFactory(client=self.client)
        return AttendanceFactory(
            client=self.client, workshop=self.workshop, vehicle=vehicle, **kwargs
        )

    def budgeted(self, attendance=None, *, with_items=True):
        attendance = attendance or self.requested()
        budget = BudgetFactory(attendance=attendance)
        if with_items:
            service = WorkshopServiceFactory(workshop=self.workshop)
            budget.service_item = BudgetItemFactory(
                budget=budget,
                item_type="service",
                workshop_service=service,
                description="Troca de óleo",
                unit_price="100.00",
            )
            product = ProductFactory(workshop=self.workshop)
            budget.part_item = BudgetItemFactory(
                budget=budget,
                item_type="product",
                product=product,
                service_item=budget.service_item,
                description="Filtro",
                quantity="2",
                unit_price="30.00",
            )
        attendance.refresh_from_db()
        return attendance, budget

    def waiting(self, attendance=None):
        attendance, budget = self.budgeted(attendance)
        move(attendance, AttendanceStatus.WAITING_APPROVAL)
        return attendance, budget

    def approved(self, attendance=None):
        attendance, budget = self.waiting(attendance)
        budget.status_budget = BudgetStatus.APPROVED
        budget.save(update_fields=["status_budget"])
        attendance.refresh_from_db()
        return attendance, budget

    def in_progress(self, attendance=None):
        attendance, budget = self.approved(attendance)
        move(attendance, AttendanceStatus.IN_PROGRESS)
        return attendance, budget

    def completed(self, attendance=None):
        attendance, budget = self.in_progress(attendance)
        for item in (budget.service_item, budget.part_item):
            item.execution_status = "executed"
            item.save(update_fields=["execution_status"])
        move(attendance, AttendanceStatus.COMPLETED)
        return attendance, budget

    def delivered(self, attendance=None):
        attendance, budget = self.completed(attendance)
        move(attendance, AttendanceStatus.DELIVERED)
        return attendance, budget

    def at(self, status):
        if status == "requested":
            return self.requested(), None
        return getattr(self, status)()


@pytest.fixture
def flow(client_account, ready_workshop):
    return Flow(client_account, ready_workshop)
