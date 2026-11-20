"""Casos de uso de atendimento e orçamento (BE-045…BE-054).

O banco é a autoridade da máquina de estados (`attendance_transition_allowed`,
triggers de BUDGET/BUDGET_ITEM): o serviço faz o UPDATE e deixa o banco validar;
as mensagens dele chegam ao cliente em 409 (`db_errors`). A aplicação acrescenta
só o que o banco não sabe: dono do recurso, perfil e as regras abaixo marcadas
como "regra da aplicação".

Notificações (BE-070): `apps.notifications.events`, chamadas aqui dentro da
transação; a gravação só acontece depois do commit.
"""

from decimal import Decimal

from apps.accounts.models import AccountStatus, Workshop
from apps.attendances.models import (
    Attendance,
    AttendanceStatus,
    Budget,
    BudgetItem,
    BudgetItemType,
    BudgetStatus,
)
from apps.catalog.models import Product, WorkshopService
from apps.core.exceptions import ApiConflict, ApiValidationFailure
from apps.core.transactions import transactional
from apps.notifications import events
from apps.vehicles.models import Vehicle
from apps.workshops.domain import is_setup_complete
from django.db.models import Q
from django.utils import timezone

FINAL_STATUSES = (AttendanceStatus.DELIVERED, AttendanceStatus.CANCELED)
BUDGET_LOCKED = "O orçamento já foi enviado ao cliente e não pode mais ser alterado."
BUDGET_NOT_PENDING = (
    "Somente orçamentos pendentes podem ser alterados (status: {status})."
)
ALREADY_APPROVED = "Este orçamento já foi aprovado."
ALREADY_REJECTED = "Este orçamento já foi recusado."


def _lock_attendance(attendance_id: int) -> Attendance:
    return Attendance.objects.select_for_update().get(pk=attendance_id)


def _set_status(attendance: Attendance, status: str) -> Attendance:
    if attendance.status_attendance == status:
        # A trigger ignora UPDATE para o mesmo status; repetir a ação é conflito.
        label = AttendanceStatus(status).label.lower()
        raise ApiConflict(f"O atendimento já está com o status “{label}”.")
    attendance.status_attendance = status
    attendance.save(update_fields=["status_attendance"])
    attendance.refresh_from_db(fields=["status_attendance"])
    return attendance


# ------------------------------------------------------------------ cliente


@transactional
def request_attendance(client_id: int, data: dict) -> Attendance:
    """BE-045: atendimento `requested` para um veículo do cliente numa oficina apta."""
    vehicle = Vehicle.objects.filter(pk=data["id_vehicle"], client_id=client_id).first()
    if vehicle is None:
        raise ApiValidationFailure({"id_vehicle": ["Veículo não encontrado."]})

    workshop = Workshop.objects.filter(pk=data["id_workshop"]).first()
    if (
        workshop is None
        or workshop.status != AccountStatus.ACTIVE
        or not is_setup_complete(workshop)
    ):
        raise ApiValidationFailure(
            {"id_workshop": ["Oficina indisponível para atendimento."]}
        )

    attendance = Attendance.objects.create(
        client_id=client_id,
        vehicle=vehicle,
        workshop=workshop,
        mileage_km=data.get("mileage_km"),
        observations=data.get("observations"),
    )
    events.attendance_requested(attendance)
    return attendance


@transactional
def cancel_attendance(attendance: Attendance) -> Attendance:
    """BE-047 (cliente): a trigger cancela os orçamentos. A oficina cancela pela
    transição (`transition_attendance`)."""
    attendance = _lock_attendance(attendance.pk)
    attendance = _set_status(attendance, AttendanceStatus.CANCELED)
    events.attendance_canceled_by_client(attendance)
    return attendance


@transactional
def respond_budget(budget: Budget, *, approve: bool) -> Budget:
    """BE-048: aprovar/recusar. O banco exige `waiting_approval`, validade e itens na
    aprovação e sincroniza o atendimento; `date_response` é preenchida pela trigger."""
    attendance = _lock_attendance(budget.attendance_id)
    budget = Budget.objects.select_for_update().get(pk=budget.pk)
    target = BudgetStatus.APPROVED if approve else BudgetStatus.REJECTED
    if budget.status_budget == target:
        # Regra da aplicação (como no cancelamento): a trigger ignora UPDATE sem mudança
        # de status, e o segundo clique responderia 200 e notificaria a oficina de novo.
        raise ApiConflict(ALREADY_APPROVED if approve else ALREADY_REJECTED)
    if (
        not approve
        and budget.status_budget == BudgetStatus.PENDING
        and attendance.status_attendance != AttendanceStatus.WAITING_APPROVAL
    ):
        # Regra da aplicação: o cliente só recusa a proposta que a oficina enviou.
        raise ApiConflict("Este orçamento ainda não foi enviado pela oficina.")
    budget.status_budget = target
    budget.save(update_fields=["status_budget"])
    budget.refresh_from_db()
    events.budget_responded(budget, approved=approve)
    return budget


# ------------------------------------------------------------------ oficina


@transactional
def update_attendance(attendance: Attendance, data: dict) -> Attendance:
    """BE-049: quilometragem e observações técnicas. O status nunca muda por aqui."""
    attendance = _lock_attendance(attendance.pk)
    if attendance.status_attendance in FINAL_STATUSES:
        raise ApiConflict(
            "Atendimentos entregues ou cancelados não podem ser alterados."
        )
    fields = [field for field in ("mileage_km", "technical_notes") if field in data]
    for field in fields:
        setattr(attendance, field, data[field])
    if fields:
        attendance.save(update_fields=fields)
    return attendance


@transactional
def transition_attendance(attendance: Attendance, status: str) -> Attendance:
    """BE-050: `in_progress`, `completed`, `delivered`, `canceled` (e reabertura
    `completed → in_progress`). Na entrega o banco gera o histórico; aqui a km do
    veículo é atualizada se a do atendimento for maior."""
    attendance = _lock_attendance(attendance.pk)
    previous = attendance.status_attendance
    attendance = _set_status(attendance, status)

    if status == AttendanceStatus.DELIVERED and attendance.mileage_km is not None:
        Vehicle.objects.filter(
            Q(mileage_km__lt=attendance.mileage_km) | Q(mileage_km__isnull=True),
            pk=attendance.vehicle_id,
        ).update(mileage_km=attendance.mileage_km)
    events.attendance_status_changed(attendance, previous)
    return attendance


@transactional
def create_budget(attendance: Attendance, data: dict) -> Budget:
    """BE-051: orçamento `pending` (total 0, validade padrão +7 dias); o atendimento
    vai a `budgeted`. Status não permitido ou outro pendente → 409 do banco."""
    _lock_attendance(attendance.pk)
    values = {
        key: data[key]
        for key in ("date_validity", "observations")
        if data.get(key) is not None
    }
    budget = Budget.objects.create(
        attendance_id=attendance.pk, workshop_id=attendance.workshop_id, **values
    )
    budget.refresh_from_db()
    return budget


def _editable_budget(budget_id: int) -> Budget:
    """Orçamento pendente e ainda não enviado (atendimento `budgeted`).

    Regra da aplicação (RB-08, "imutáveis após o envio"): a trigger só protege o
    orçamento que deixou de ser `pending`, mas depois do envio ele continua
    `pending` (aguardando o cliente) e não pode mais mudar.
    """
    budget = (
        Budget.objects.select_for_update()
        .select_related("attendance")
        .get(pk=budget_id)
    )
    if budget.status_budget != BudgetStatus.PENDING:
        raise ApiConflict(BUDGET_NOT_PENDING.format(status=budget.status_budget))
    if budget.attendance.status_attendance != AttendanceStatus.BUDGETED:
        raise ApiConflict(BUDGET_LOCKED)
    return budget


@transactional
def update_budget(budget: Budget, data: dict) -> Budget:
    """BE-051: validade (futura) e observações do orçamento em edição."""
    _lock_attendance(budget.attendance_id)
    budget = _editable_budget(budget.pk)
    fields = [field for field in ("date_validity", "observations") if field in data]
    for field in fields:
        setattr(budget, field, data[field])
    if fields:
        budget.save(update_fields=fields)  # nunca reenviar total_price
    budget.refresh_from_db()
    return budget


def _resolve_item(
    budget: Budget, data: dict, current: BudgetItem | None = None
) -> dict:
    """Valida tipo, vínculos de catálogo (mesma oficina) e preenche padrões do catálogo."""
    item_type = data["item_type"]
    errors = {}
    values = {
        "item_type": item_type,
        "workshop_service_id": None,
        "product_id": None,
        "service_item_id": None,
    }
    default_description = default_price = None

    service_id, product_id, parent_id = (
        data.get("id_workshop_service"),
        data.get("id_product"),
        data.get("id_service_item"),
    )

    if item_type == BudgetItemType.SERVICE:
        if product_id is not None:
            errors["id_product"] = ["Item de serviço não referencia produto."]
        service = (
            WorkshopService.objects.filter(
                pk=service_id, workshop_id=budget.workshop_id
            )
            .select_related("service")
            .first()
            if service_id
            else None
        )
        if service is None:
            errors["id_workshop_service"] = ["Escolha um serviço da sua oficina."]
        else:
            values["workshop_service_id"] = service.pk
            default_description = service.name_local or service.service.name
            default_price = service.price_base
    elif item_type == BudgetItemType.PRODUCT:
        if service_id is not None:
            errors["id_workshop_service"] = ["Item de produto não referencia serviço."]
        product = (
            Product.objects.filter(
                pk=product_id, workshop_id=budget.workshop_id
            ).first()
            if product_id
            else None
        )
        if product is None:
            errors["id_product"] = ["Escolha um produto da sua oficina."]
        else:
            values["product_id"] = product.pk
            default_description, default_price = product.name, product.price
    else:
        for field in ("id_workshop_service", "id_product"):
            if data.get(field) is not None:
                errors[field] = [
                    "Mão de obra e outros valores não referenciam o catálogo."
                ]

    if parent_id is not None:
        if item_type != BudgetItemType.PRODUCT:
            errors["id_service_item"] = [
                "Só produtos/peças podem pertencer a um serviço."
            ]
        elif (
            not BudgetItem.objects.filter(
                pk=parent_id, budget_id=budget.pk, item_type=BudgetItemType.SERVICE
            )
            .exclude(pk=getattr(current, "pk", None))
            .exists()
        ):
            errors["id_service_item"] = [
                "O serviço informado não é um item deste orçamento."
            ]
        else:
            values["service_item_id"] = parent_id

    description = (data.get("description") or "").strip() or default_description
    if not description:
        errors["description"] = ["Informe a descrição do item."]
    unit_price = data.get("unit_price", default_price)
    if unit_price is None:
        errors["unit_price"] = ["Informe o valor unitário."]

    if errors:
        raise ApiValidationFailure(errors)

    values.update(
        description=description[:255],
        quantity=data.get("quantity", Decimal("1")),
        unit_price=unit_price,
    )
    return values


@transactional
def add_budget_item(budget: Budget, data: dict) -> BudgetItem:
    """BE-052: inclui item (o banco recalcula `total_price`)."""
    _lock_attendance(budget.attendance_id)
    budget = _editable_budget(budget.pk)
    values = _resolve_item(budget, data)
    return BudgetItem.objects.create(
        budget=budget, workshop_id=budget.workshop_id, **values
    )


@transactional
def update_budget_item(item: BudgetItem, data: dict) -> BudgetItem:
    """BE-052: edição parcial (os campos ausentes mantêm o valor atual)."""
    budget = Budget.objects.get(pk=item.budget_id)
    _lock_attendance(budget.attendance_id)
    budget = _editable_budget(budget.pk)
    item = BudgetItem.objects.select_for_update().get(pk=item.pk)
    merged = {
        "item_type": item.item_type,
        "id_workshop_service": item.workshop_service_id,
        "id_product": item.product_id,
        "id_service_item": item.service_item_id,
        "description": item.description,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
    }
    merged.update(data)
    if (
        merged["item_type"] != item.item_type
        and item.item_type == BudgetItemType.SERVICE
    ):
        if item.parts.exists():
            raise ApiConflict(
                "Remova ou desvincule as peças deste serviço antes de mudar o tipo do item."
            )
    values = _resolve_item(budget, merged, current=item)
    for field, value in values.items():
        setattr(item, field, value)
    item.save(update_fields=list(values))
    return item


@transactional
def remove_budget_item(item: BudgetItem) -> None:
    """BE-052: remove o item; um serviço leva junto as peças ligadas a ele (mesma
    instrução: a FK das peças é NO ACTION e aceita a remoção conjunta)."""
    budget = Budget.objects.get(pk=item.budget_id)
    _lock_attendance(budget.attendance_id)
    _editable_budget(budget.pk)
    BudgetItem.objects.filter(
        Q(pk=item.pk) | Q(service_item_id=item.pk), budget_id=budget.pk
    ).delete()


@transactional
def send_budget(budget: Budget) -> Budget:
    """BE-053: "enviar" = atendimento `budgeted → waiting_approval` (o banco exige itens)."""
    attendance = _lock_attendance(budget.attendance_id)
    budget = Budget.objects.select_for_update().get(pk=budget.pk)
    if budget.status_budget != BudgetStatus.PENDING:
        raise ApiConflict(BUDGET_NOT_PENDING.format(status=budget.status_budget))
    if attendance.status_attendance != AttendanceStatus.BUDGETED:
        raise ApiConflict("Este orçamento já foi enviado ao cliente.")
    if budget.date_validity <= timezone.now():
        raise ApiConflict(
            "O orçamento está fora da validade: atualize a validade antes de enviar."
        )
    _set_status(attendance, AttendanceStatus.WAITING_APPROVAL)
    budget.refresh_from_db()
    events.budget_sent(budget)
    return budget


@transactional
def set_item_execution(item: BudgetItem, execution_status: str) -> BudgetItem:
    """BE-054: executado / não executado / pendente. Só serviço e produto (geram histórico);
    fora de `in_progress` o banco recusa (409). `executed_at` é preenchido pela trigger."""
    if item.item_type not in (BudgetItemType.SERVICE, BudgetItemType.PRODUCT):
        raise ApiValidationFailure(
            {"execution_status": ["Só serviços e produtos têm situação de execução."]}
        )
    budget = Budget.objects.get(pk=item.budget_id)
    _lock_attendance(budget.attendance_id)
    item = BudgetItem.objects.select_for_update().get(pk=item.pk)
    item.execution_status = execution_status
    item.save(update_fields=["execution_status"])
    item.refresh_from_db()
    return item
