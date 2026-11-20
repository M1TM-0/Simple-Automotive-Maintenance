from apps.core.fields import StoredImageField
from django.db import models


class EstablishmentType(models.TextChoices):
    WORKSHOP = "oficina", "Oficina"
    TIRE_SHOP = "borracharia", "Borracharia"
    GAS_STATION = "posto_combustivel", "Posto de combustível"
    PARTS_STORE = "loja_autopecas", "Loja de autopeças"
    AUTO_CENTER = "centro_automotivo", "Centro automotivo"
    DEALERSHIP = "concessionaria", "Concessionária"
    CAR_WASH = "lava_jato", "Lava-jato"
    OTHER = "outro", "Outro"


class PointOfInterest(models.Model):
    id_point_of_interest = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=30, choices=EstablishmentType.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.TextField(null=True, blank=True)
    external_source = models.CharField(max_length=50, null=True, blank=True)
    external_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "point_of_interest"
        managed = False


class PagWorkshop(models.Model):
    id_pag_workshop = models.BigAutoField(primary_key=True)
    workshop = models.OneToOneField(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="page",
    )
    description = models.TextField(null=True, blank=True)
    photo_profile = StoredImageField(db_default="default-profile.png")
    photo_banner = StoredImageField()

    class Meta:
        db_table = "pag_workshop"
        managed = False


class OperationHour(models.Model):
    id_operation_hour = models.BigAutoField(primary_key=True)
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="operation_hours",
    )
    day_of_week = models.IntegerField()
    opening_time = models.TimeField()
    closing_time = models.TimeField()

    class Meta:
        db_table = "operation_hour"
        managed = False
