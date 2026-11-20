from decimal import Decimal

from apps.core.db import CurrentTimestamp, timestamp_plus_days
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Round


class AttendanceStatus(models.TextChoices):
    REQUESTED = "requested", "Solicitado"
    BUDGETED = "budgeted", "Orçado"
    WAITING_APPROVAL = "waiting_approval", "Aguardando aprovação"
    APPROVED = "approved", "Aprovado"
    IN_PROGRESS = "in_progress", "Em andamento"
    COMPLETED = "completed", "Concluído"
    DELIVERED = "delivered", "Entregue"
    CANCELED = "canceled", "Cancelado"


class BudgetStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    APPROVED = "approved", "Aprovado"
    REJECTED = "rejected", "Recusado"
    CANCELLED = "cancelled", "Cancelado"
    EXPIRED = "expired", "Expirado"


class BudgetItemType(models.TextChoices):
    SERVICE = "service", "Serviço"
    PRODUCT = "product", "Produto"
    LABOR = "labor", "Mão de obra"
    OTHER = "other", "Outro"


class ExecutionStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    EXECUTED = "executed", "Executado"
    NOT_EXECUTED = "not_executed", "Não executado"


class Attendance(models.Model):
    id_attendance = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(
        "accounts.Client",
        db_column="id_client",
        on_delete=models.DO_NOTHING,
        related_name="attendances",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        db_column="id_vehicle",
        on_delete=models.DO_NOTHING,
        related_name="attendances",
    )
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="attendances",
    )
    date_attendance = models.DateTimeField(db_default=CurrentTimestamp())
    status_attendance = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        db_default=AttendanceStatus.REQUESTED.value,
    )
    mileage_km = models.IntegerField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)
    technical_notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "attendance"
        managed = False


class Budget(models.Model):
    """`total_price` só pode ser alterado pelo trigger dos itens.

    Salve com `update_fields` para não reenviar um total desatualizado.
    """

    id_budget = models.BigAutoField(primary_key=True)
    attendance = models.ForeignKey(
        Attendance,
        db_column="id_attendance",
        on_delete=models.DO_NOTHING,
        related_name="budgets",
    )
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="budgets",
    )
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())
    date_validity = models.DateTimeField(db_default=timestamp_plus_days(7))
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2, db_default=Decimal("0")
    )
    status_budget = models.CharField(
        max_length=50,
        choices=BudgetStatus.choices,
        db_default=BudgetStatus.PENDING.value,
    )
    date_response = models.DateTimeField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "budget"
        managed = False


class BudgetItem(models.Model):
    id_budget_item = models.BigAutoField(primary_key=True)
    budget = models.ForeignKey(
        Budget,
        db_column="id_budget",
        on_delete=models.DO_NOTHING,
        related_name="items",
    )
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="budget_items",
    )
    item_type = models.CharField(max_length=20, choices=BudgetItemType.choices)
    workshop_service = models.ForeignKey(
        "catalog.WorkshopService",
        db_column="id_workshop_service",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="budget_items",
    )
    product = models.ForeignKey(
        "catalog.Product",
        db_column="id_product",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="budget_items",
    )
    service_item = models.ForeignKey(
        "self",
        db_column="id_service_item",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="parts",
    )
    service_item_type = models.GeneratedField(
        expression=Case(
            When(Q(service_item__isnull=False), then=Value("service")),
            output_field=models.CharField(max_length=20),
        ),
        output_field=models.CharField(max_length=20, null=True),
        db_persist=True,
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, db_default=Decimal("1")
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.GeneratedField(
        expression=Round(F("quantity") * F("unit_price"), precision=2),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
    )
    execution_status = models.CharField(
        max_length=20,
        choices=ExecutionStatus.choices,
        db_default=ExecutionStatus.PENDING.value,
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=CurrentTimestamp())

    class Meta:
        db_table = "budget_item"
        managed = False
