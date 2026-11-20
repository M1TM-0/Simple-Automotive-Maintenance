"""Manutenção preventiva: próximas manutenções e lembretes (BE-077, RN06, DP-05).

**Cálculo (função pura `upcoming_maintenance`).** Os registros de serviço do
histórico são agrupados por item: o serviço do catálogo (`id_service`) ou, sem
ele, o nome normalizado (`normalize_service_name`). Para cada item:

- última execução = o registro mais recente (data, depois id) — feito pela oficina
  (atendimento entregue) ou informado pelo cliente;
- intervalo = o `interval_km` mais recente informado para o item (a oficina não
  informa intervalo: o do cliente continua valendo para as trocas seguintes);
- próxima = km da última execução + intervalo; faltam = próxima − km atual
  (o maior entre a km do veículo e a da última execução);
- situação: `overdue` (faltam ≤ 0), `soon` (faltam ≤ `SAM_MAINTENANCE_REMINDER_PERCENT`
  % do intervalo) ou `ok`.

Itens sem intervalo, ou cuja última execução não tem km, ficam de fora (não há
base para calcular). Só quilometragem: não há intervalo em tempo no schema. Peças
não entram (o intervalo é do serviço).

**Lembrete (`send_due_reminders`).** Itens `soon`/`overdue` de veículos de clientes
ativos geram uma notificação para o cliente, **uma vez por ciclo**: a tabela
`MAINTENANCE_REMINDER` tem a última execução como chave única (`INSERT … ON
CONFLICT DO NOTHING`); só quem inseriu notifica. Uma execução nova do item abre
outro ciclo. A rotina roda no serviço `jobs` (`send_maintenance_reminders`).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby

from apps.accounts.models import AccountStatus
from apps.core.transactions import transactional
from apps.core.validators import normalize_service_name
from apps.vehicles.models import (
    MaintenanceReminder,
    RegisterMaintenance,
    ReminderStatus,
    Vehicle,
)
from django.conf import settings
from django.db import connection
from django.db.models import Exists, OuterRef

OK = "ok"
SOON = ReminderStatus.SOON.value
OVERDUE = ReminderStatus.OVERDUE.value


@dataclass(frozen=True)
class Execution:
    """Um registro de serviço do histórico (REGISTER_MAINTENANCE)."""

    record_id: int
    service_name: str
    date: datetime
    mileage_km: int | None
    interval_km: int | None
    service_id: int | None = None


@dataclass(frozen=True)
class Upcoming:
    """Próxima manutenção de um item do veículo."""

    last_record_id: int
    service_id: int | None
    service_name: str
    last_date: datetime
    last_mileage_km: int
    interval_km: int
    next_mileage_km: int
    current_mileage_km: int
    remaining_km: int
    progress_percent: int
    status: str


def item_key(execution: Execution):
    if execution.service_id is not None:
        return ("service", execution.service_id)
    return ("name", normalize_service_name(execution.service_name))


def reminder_threshold_km(interval_km: int) -> int:
    return interval_km * settings.SAM_MAINTENANCE_REMINDER_PERCENT // 100


def classify(remaining_km: int, interval_km: int) -> str:
    if remaining_km <= 0:
        return OVERDUE
    if remaining_km <= reminder_threshold_km(interval_km):
        return SOON
    return OK


def upcoming_maintenance(executions, current_mileage_km: int | None) -> list[Upcoming]:
    """Próximas manutenções por item, mais urgente primeiro."""
    groups = defaultdict(list)
    for execution in executions:
        groups[item_key(execution)].append(execution)

    result = []
    for items in groups.values():
        items.sort(key=lambda e: (e.date, e.record_id))
        interval = next((e.interval_km for e in reversed(items) if e.interval_km), None)
        last = items[-1]
        if interval is None or last.mileage_km is None:
            continue
        current = max(current_mileage_km or 0, last.mileage_km)
        next_km = last.mileage_km + interval
        remaining = next_km - current
        used = current - last.mileage_km
        result.append(
            Upcoming(
                last_record_id=last.record_id,
                service_id=last.service_id,
                service_name=last.service_name,
                last_date=last.date,
                last_mileage_km=last.mileage_km,
                interval_km=interval,
                next_mileage_km=next_km,
                current_mileage_km=current,
                remaining_km=remaining,
                progress_percent=max(0, min(100, used * 100 // interval)),
                status=classify(remaining, interval),
            )
        )
    return sorted(
        result, key=lambda u: (u.remaining_km, u.service_name.lower(), u.last_record_id)
    )


# ------------------------------------------------------------------- leitura

_EXECUTION_FIELDS = (
    "vehicle_id",
    "id_register_maintenance",
    "service_name",
    "date_maintenance",
    "mileage_km",
    "interval_km",
    "service_id",
)


def _execution(row) -> Execution:
    _, record_id, name, date, mileage, interval, service_id = row
    return Execution(record_id, name, date, mileage, interval, service_id)


def vehicle_upcoming(vehicle: Vehicle) -> list[Upcoming]:
    """`GET /vehicles/{id}/upcoming-maintenance/`: uma consulta, cálculo em Python."""
    rows = RegisterMaintenance.objects.filter(vehicle_id=vehicle.pk).values_list(
        *_EXECUTION_FIELDS
    )
    return upcoming_maintenance([_execution(row) for row in rows], vehicle.mileage_km)


def reminders_sent(record_ids) -> dict:
    """`{id da última execução: data do lembrete}` dos ciclos já avisados."""
    return dict(
        MaintenanceReminder.objects.filter(
            register_maintenance_id__in=list(record_ids)
        ).values_list("register_maintenance_id", "date_sent")
    )


# -------------------------------------------------------------------- rotina


def _due_items():
    """`(veículo, item)` em `soon`/`overdue` de clientes ativos, sem lembrete no ciclo."""
    with_interval = RegisterMaintenance.objects.filter(
        vehicle_id=OuterRef("pk"), interval_km__isnull=False
    )
    vehicles = {
        vehicle.pk: vehicle
        for vehicle in Vehicle.objects.filter(
            Exists(with_interval), client__status=AccountStatus.ACTIVE
        )
    }
    if not vehicles:
        return []
    rows = (
        RegisterMaintenance.objects.filter(vehicle_id__in=list(vehicles))
        .order_by("vehicle_id")
        .values_list(*_EXECUTION_FIELDS)
    )
    due = []
    for vehicle_id, vehicle_rows in groupby(rows, key=lambda row: row[0]):
        vehicle = vehicles[vehicle_id]
        for item in upcoming_maintenance(
            [_execution(r) for r in vehicle_rows], vehicle.mileage_km
        ):
            if item.status != OK:
                due.append((vehicle, item))
    already = reminders_sent(item.last_record_id for _, item in due)
    return [
        (vehicle, item) for vehicle, item in due if item.last_record_id not in already
    ]


@transactional
def _record_and_notify(vehicle: Vehicle, item: Upcoming) -> bool:
    from apps.notifications import events

    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO maintenance_reminder (id_register_maintenance, due_mileage_km, status_reminder) "
            "VALUES (%s, %s, %s) ON CONFLICT (id_register_maintenance) DO NOTHING "
            "RETURNING id_maintenance_reminder",
            [item.last_record_id, item.next_mileage_km, item.status],
        )
        if cursor.fetchone() is None:  # outra execução da rotina já avisou este ciclo
            return False
    events.maintenance_due(vehicle, item)
    return True


def send_due_reminders() -> int:
    """Envia os lembretes pendentes; devolve quantos foram enviados. Idempotente."""
    return sum(_record_and_notify(vehicle, item) for vehicle, item in _due_items())
