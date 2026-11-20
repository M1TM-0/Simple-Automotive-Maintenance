"""Leituras do histórico do veículo (BE-044, BE-056)."""

from apps.accounts.models import Workshop
from apps.vehicles.models import VehicleMaintenanceHistory
from django.db.models import OuterRef, Subquery


def vehicle_history(vehicle_id: int):
    """Serviços e peças do veículo, mais recente primeiro (ordem determinística)."""
    workshop_name = Workshop.objects.filter(pk=OuterRef("id_workshop")).values(
        "name_fantasy"
    )[:1]
    return (
        VehicleMaintenanceHistory.objects.filter(id_vehicle=vehicle_id)
        .annotate(workshop_name=Subquery(workshop_name))
        .order_by("-date_maintenance", "record_type", "-id_record")
    )
