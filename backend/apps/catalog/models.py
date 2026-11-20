from apps.core.db import CurrentTimestamp
from apps.core.fields import StoredImageField
from django.db import models


class SolicitationStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    APPROVED = "approved", "Aprovada"
    REJECTED = "rejected", "Rejeitada"


class ServiceCategory(models.Model):
    id_service_category = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "service_category"
        managed = False


class Service(models.Model):
    id_service = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    category = models.ForeignKey(
        ServiceCategory,
        db_column="id_category",
        on_delete=models.DO_NOTHING,
        related_name="services",
    )
    active = models.BooleanField(db_default=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "service"
        managed = False


class WorkshopService(models.Model):
    id_workshop_service = models.BigAutoField(primary_key=True)
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="services",
    )
    service = models.ForeignKey(
        Service,
        db_column="id_service",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="workshop_services",
    )
    name_local = models.CharField(max_length=255, null=True, blank=True)
    description_local = models.TextField(null=True, blank=True)
    suggested_category = models.ForeignKey(
        ServiceCategory,
        db_column="id_suggested_category",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="suggested_services",
    )
    price_base = models.DecimalField(max_digits=10, decimal_places=2)
    duration_estimate = models.IntegerField()
    disponibility = models.BooleanField(db_default=True)
    status_solicitation = models.CharField(
        max_length=50,
        choices=SolicitationStatus.choices,
        null=True,
        blank=True,
    )
    motivation_rejection = models.TextField(null=True, blank=True)
    date_solicitation_response = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=CurrentTimestamp())

    class Meta:
        db_table = "workshop_service"
        managed = False


class Product(models.Model):
    id_product = models.BigAutoField(primary_key=True)
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    category = models.CharField(max_length=255, null=True, blank=True)
    brand = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    disponibility = models.BooleanField(db_default=True)
    photo = StoredImageField()
    created_at = models.DateTimeField(db_default=CurrentTimestamp())
    active = models.BooleanField(db_default=True)

    class Meta:
        db_table = "product"
        managed = False
