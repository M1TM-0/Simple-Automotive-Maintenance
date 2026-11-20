from apps.core.db import CurrentTimestamp
from apps.core.fields import StoredImageField
from django.db import models


class Fuel(models.TextChoices):
    GASOLINE = "gasolina", "Gasolina"
    ETHANOL = "etanol", "Etanol"
    DIESEL = "diesel", "Diesel"
    FLEX = "flex", "Flex"
    ELECTRIC = "eletrico", "Elétrico"
    HYBRID = "hibrido", "Híbrido"
    CNG = "gnv", "GNV"
    OTHER = "outro", "Outro"


class Exchange(models.TextChoices):
    MANUAL = "manual", "Manual"
    AUTOMATIC = "automatico", "Automático"
    AUTOMATED = "automatizado", "Automatizado"
    DUAL_CLUTCH = "dupla_embreagem", "Dupla embreagem"
    CVT = "variavel", "Variável (CVT)"
    OTHER = "outro", "Outro"


class Vehicle(models.Model):
    id_vehicle = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(
        "accounts.Client",
        db_column="id_client",
        on_delete=models.DO_NOTHING,
        related_name="vehicles",
    )
    brand = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    year_fabrication = models.IntegerField()
    year_model = models.IntegerField()
    plate = models.CharField(max_length=7)
    fuel = models.CharField(max_length=20, choices=Fuel.choices)
    exchange = models.CharField(max_length=20, choices=Exchange.choices)
    version = models.CharField(max_length=255, null=True, blank=True)
    motorization = models.CharField(max_length=255, null=True, blank=True)
    color = models.CharField(max_length=20, null=True, blank=True)
    information = models.TextField(null=True, blank=True)
    photo_1 = StoredImageField()
    photo_2 = StoredImageField()
    photo_3 = StoredImageField()
    mileage_km = models.IntegerField(null=True, blank=True)
    history_shared = models.BooleanField(db_default=False)

    class Meta:
        db_table = "vehicle"
        managed = False


class RegisterMaintenance(models.Model):
    id_register_maintenance = models.BigAutoField(primary_key=True)
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="id_vehicle",
        on_delete=models.DO_NOTHING,
        related_name="maintenances",
    )
    attendance = models.ForeignKey(
        "attendances.Attendance",
        db_column="id_attendance",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="maintenances",
    )
    budget = models.ForeignKey(
        "attendances.Budget",
        db_column="id_budget",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="maintenances",
    )
    budget_item = models.OneToOneField(
        "attendances.BudgetItem",
        db_column="id_budget_item",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="maintenance",
    )
    service = models.ForeignKey(
        "catalog.Service",
        db_column="id_service",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="maintenances",
    )
    service_name = models.CharField(max_length=255)
    date_maintenance = models.DateTimeField(db_default=CurrentTimestamp())
    mileage_km = models.IntegerField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)
    interval_km = models.IntegerField(null=True, blank=True)
    item_type = models.GeneratedField(
        expression=models.Case(
            models.When(
                models.Q(budget_item__isnull=False),
                then=models.Value("service"),
            ),
            output_field=models.CharField(max_length=20),
        ),
        output_field=models.CharField(max_length=20, null=True),
        db_persist=True,
    )
    item_execution_status = models.GeneratedField(
        expression=models.Case(
            models.When(
                models.Q(budget_item__isnull=False),
                then=models.Value("executed"),
            ),
            output_field=models.CharField(max_length=20),
        ),
        output_field=models.CharField(max_length=20, null=True),
        db_persist=True,
    )

    class Meta:
        db_table = "register_maintenance"
        managed = False


class RegisterMaintenancePart(models.Model):
    id_register_maintenance_part = models.BigAutoField(primary_key=True)
    vehicle = models.ForeignKey(
        Vehicle,
        db_column="id_vehicle",
        on_delete=models.DO_NOTHING,
        related_name="maintenance_parts",
    )
    attendance = models.ForeignKey(
        "attendances.Attendance",
        db_column="id_attendance",
        on_delete=models.DO_NOTHING,
        related_name="maintenance_parts",
    )
    budget = models.ForeignKey(
        "attendances.Budget",
        db_column="id_budget",
        on_delete=models.DO_NOTHING,
        related_name="maintenance_parts",
    )
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="maintenance_parts",
    )
    budget_item = models.OneToOneField(
        "attendances.BudgetItem",
        db_column="id_budget_item",
        on_delete=models.DO_NOTHING,
        related_name="maintenance_part",
    )
    service_item = models.ForeignKey(
        "attendances.BudgetItem",
        db_column="id_service_item",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="used_parts",
    )
    product = models.ForeignKey(
        "catalog.Product",
        db_column="id_product",
        on_delete=models.DO_NOTHING,
        related_name="maintenance_parts",
    )
    description = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    date_maintenance = models.DateTimeField(db_default=CurrentTimestamp())
    mileage_km = models.IntegerField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)
    item_type = models.GeneratedField(
        expression=models.Value(
            "product", output_field=models.CharField(max_length=20)
        ),
        output_field=models.CharField(max_length=20),
        db_persist=True,
    )
    item_execution_status = models.GeneratedField(
        expression=models.Value(
            "executed", output_field=models.CharField(max_length=20)
        ),
        output_field=models.CharField(max_length=20),
        db_persist=True,
    )

    class Meta:
        db_table = "register_maintenance_part"
        managed = False


class ReminderStatus(models.TextChoices):
    SOON = "soon", "Próxima"
    OVERDUE = "overdue", "Vencida"


class MaintenanceReminder(models.Model):
    """Lembrete de manutenção preventiva já enviado (BE-077; tabela de `vehicles/0004`).

    Um por "ciclo": a chave é a última execução do item (`REGISTER_MAINTENANCE`) a
    partir da qual a próxima foi calculada. Uma execução nova abre outro ciclo.
    """

    id_maintenance_reminder = models.BigAutoField(primary_key=True)
    register_maintenance = models.OneToOneField(
        RegisterMaintenance,
        db_column="id_register_maintenance",
        on_delete=models.DO_NOTHING,
        related_name="reminder",
    )
    due_mileage_km = models.IntegerField()
    status_reminder = models.CharField(max_length=20, choices=ReminderStatus.choices)
    date_sent = models.DateTimeField(db_default=CurrentTimestamp())

    class Meta:
        db_table = "maintenance_reminder"
        managed = False


class VehicleMaintenanceHistory(models.Model):
    """Leitura de vw_vehicle_maintenance_history (serviços e peças em uma lista)."""

    pk = models.CompositePrimaryKey("record_type", "id_record")
    record_type = models.CharField(max_length=10)
    id_record = models.BigIntegerField()
    id_vehicle = models.BigIntegerField()
    id_attendance = models.BigIntegerField(null=True)
    id_budget = models.BigIntegerField(null=True)
    id_budget_item = models.BigIntegerField(null=True)
    id_workshop = models.BigIntegerField(null=True)
    id_service = models.BigIntegerField(null=True)
    id_product = models.BigIntegerField(null=True)
    id_service_item = models.BigIntegerField(null=True)
    description = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, null=True)
    category = models.CharField(max_length=255, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    date_maintenance = models.DateTimeField()
    mileage_km = models.IntegerField(null=True)
    observations = models.TextField(null=True)
    interval_km = models.IntegerField(null=True)

    class Meta:
        db_table = "vw_vehicle_maintenance_history"
        managed = False
