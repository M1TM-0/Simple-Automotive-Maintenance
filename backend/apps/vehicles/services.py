"""Casos de uso de veículos e histórico (BE-043, BE-044)."""

from apps.attendances.models import Attendance
from apps.core.exceptions import ApiConflict, ApiValidationFailure
from apps.core.storage import apply_image_changes, delete_stored_image
from apps.core.transactions import transactional
from apps.vehicles.models import RegisterMaintenance, RegisterMaintenancePart, Vehicle
from apps.vehicles.serializers import PHOTO_FIELDS
from django.db import transaction

VEHICLE_FIELDS = (
    "brand",
    "model",
    "year_fabrication",
    "year_model",
    "plate",
    "fuel",
    "exchange",
    "version",
    "motorization",
    "color",
    "information",
    "mileage_km",
    "history_shared",
)
DUPLICATE_PLATE = "Já existe um veículo com esta placa."
VEHICLE_IN_USE = "Veículos com atendimentos ou histórico não podem ser excluídos."


def _check_plate(client_id: int, plate: str, exclude_id=None):
    duplicates = Vehicle.objects.filter(client_id=client_id, plate=plate)
    if exclude_id is not None:
        duplicates = duplicates.exclude(pk=exclude_id)
    if duplicates.exists():
        # O índice `unique_vehicle` continua sendo a garantia (corrida → mesmo 400).
        raise ApiValidationFailure({"plate": [DUPLICATE_PLATE]})


def _apply_photos(vehicle: Vehicle, data: dict):
    changes = {field: data[field] for field in PHOTO_FIELDS if field in data}
    if changes:
        apply_image_changes(vehicle, changes, folder="vehicles")


@transactional
def create_vehicle(client_id: int, data: dict) -> Vehicle:
    _check_plate(client_id, data["plate"])
    vehicle = Vehicle.objects.create(
        client_id=client_id,
        **{field: data[field] for field in VEHICLE_FIELDS if field in data},
    )
    _apply_photos(
        vehicle, {k: v for k, v in data.items() if k in PHOTO_FIELDS and v is not None}
    )
    return vehicle


@transactional
def update_vehicle(vehicle: Vehicle, data: dict) -> Vehicle:
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if "plate" in data:
        _check_plate(vehicle.client_id, data["plate"], exclude_id=vehicle.pk)
    fields = [field for field in VEHICLE_FIELDS if field in data]
    for field in fields:
        setattr(vehicle, field, data[field])
    if fields:
        vehicle.save(update_fields=fields)
    _apply_photos(vehicle, data)
    return vehicle


@transactional
def delete_vehicle(vehicle: Vehicle) -> None:
    """RN05: veículo com atendimento ou histórico não é excluído (FKs RESTRICT)."""
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    in_use = (
        Attendance.objects.filter(vehicle_id=vehicle.pk).exists()
        or RegisterMaintenance.objects.filter(vehicle_id=vehicle.pk).exists()
        or RegisterMaintenancePart.objects.filter(vehicle_id=vehicle.pk).exists()
    )
    if in_use:
        raise ApiConflict(VEHICLE_IN_USE)
    photos = [getattr(vehicle, field) for field in PHOTO_FIELDS]
    Vehicle.objects.filter(pk=vehicle.pk).delete()
    transaction.on_commit(lambda: [delete_stored_image(name) for name in photos])


@transactional
def add_manual_history(vehicle: Vehicle, data: dict) -> RegisterMaintenance:
    """Registro manual (sem atendimento de origem). Se a km informada for maior que a
    do veículo, atualiza `VEHICLE.mileage_km` (RI-11)."""
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    record = RegisterMaintenance.objects.create(
        vehicle=vehicle,
        service_id=data.get("id_service"),
        service_name=data["service_name"],
        date_maintenance=data["date_maintenance"],
        mileage_km=data.get("mileage_km"),
        observations=data.get("observations"),
        interval_km=data.get("interval_km"),
    )
    mileage = data.get("mileage_km")
    if mileage is not None and (
        vehicle.mileage_km is None or mileage > vehicle.mileage_km
    ):
        vehicle.mileage_km = mileage
        vehicle.save(update_fields=["mileage_km"])
    return record
