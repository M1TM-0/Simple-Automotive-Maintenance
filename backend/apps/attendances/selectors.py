"""Leituras de atendimentos e clientes da oficina (BE-046, BE-049, BE-055).

Consultas com número fixo de queries (prefetch), sem N+1.
"""

from apps.accounts.models import Client
from apps.attendances.models import Attendance, Budget, BudgetItem
from apps.vehicles.models import Vehicle
from django.db.models import Count, Exists, Max, OuterRef, Prefetch, Subquery

_BUDGETS_NEWEST_FIRST = Budget.objects.order_by("-date_creation", "-id_budget")


def attendance_list(**filters):
    return (
        Attendance.objects.filter(**filters)
        .select_related("workshop__page", "vehicle", "client")
        .prefetch_related(Prefetch("budgets", queryset=_BUDGETS_NEWEST_FIRST))
        .order_by("-date_attendance", "-id_attendance")
    )


def attendance_detail(**filters):
    budgets = _BUDGETS_NEWEST_FIRST.select_related("review").prefetch_related(
        Prefetch("items", queryset=BudgetItem.objects.order_by("id_budget_item"))
    )
    return (
        Attendance.objects.filter(**filters)
        .select_related("workshop__page", "vehicle", "client")
        .prefetch_related(Prefetch("budgets", queryset=budgets))
    )


def workshop_clients(workshop_id: int):
    """Clientes com ao menos um atendimento na oficina, mais recentes primeiro."""
    here = Attendance.objects.filter(
        workshop_id=workshop_id, client_id=OuterRef("pk")
    ).order_by()
    attended_vehicles = Vehicle.objects.filter(
        Exists(
            Attendance.objects.filter(
                workshop_id=workshop_id, vehicle_id=OuterRef("pk")
            )
        )
    ).order_by("brand", "model", "id_vehicle")
    return (
        Client.objects.filter(Exists(here))
        .annotate(
            attendance_count=Subquery(
                here.values("client_id")
                .annotate(total=Count("id_attendance"))
                .values("total")[:1]
            ),
            last_attendance=Subquery(
                here.values("client_id")
                .annotate(last=Max("date_attendance"))
                .values("last")[:1]
            ),
        )
        .prefetch_related(
            Prefetch(
                "vehicles", queryset=attended_vehicles, to_attr="attended_vehicles"
            )
        )
        .order_by("-last_attendance", "id_client")
    )


def workshop_client_vehicles(workshop_id: int, client_id: int):
    """Veículos do cliente atendidos pela oficina, com os atendimentos feitos nela."""
    here = Attendance.objects.filter(workshop_id=workshop_id).order_by(
        "-date_attendance", "-id_attendance"
    )
    return (
        Vehicle.objects.filter(client_id=client_id)
        .filter(
            Exists(
                Attendance.objects.filter(
                    workshop_id=workshop_id, vehicle_id=OuterRef("pk")
                )
            )
        )
        .prefetch_related(
            Prefetch("attendances", queryset=here, to_attr="workshop_attendances")
        )
        .order_by("brand", "model", "id_vehicle")
    )
