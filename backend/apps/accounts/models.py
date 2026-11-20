from apps.core.db import CurrentTimestamp
from apps.core.fields import StoredImageField
from django.db import models


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "Ativa"
    INACTIVE = "inactive", "Inativa"
    BLOCKED = "blocked", "Bloqueada"


class Client(models.Model):
    id_client = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    password_hash = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(db_default=CurrentTimestamp())
    status = models.CharField(
        max_length=50,
        choices=AccountStatus.choices,
        db_default=AccountStatus.ACTIVE.value,
    )
    photo_profile = StoredImageField()

    def __str__(self):
        return f"{self.name} <{self.email}>"

    class Meta:
        db_table = "client"
        managed = False


class Workshop(models.Model):
    id_workshop = models.BigAutoField(primary_key=True)
    name_fantasy = models.CharField(max_length=255)
    name_responsible = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    password_hash = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=255, null=True, blank=True)
    cnpj = models.CharField(max_length=14, unique=True)
    created_at = models.DateTimeField(db_default=CurrentTimestamp())
    status = models.CharField(
        max_length=50,
        choices=AccountStatus.choices,
        db_default=AccountStatus.ACTIVE.value,
    )
    point_of_interest = models.OneToOneField(
        "workshops.PointOfInterest",
        db_column="id_point_of_interest",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="workshop",
    )

    def __str__(self):
        return f"{self.name_fantasy} (CNPJ {self.cnpj})"

    class Meta:
        db_table = "workshop"
        managed = False


class Favorite(models.Model):
    id_favorite = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(
        Client,
        db_column="id_client",
        on_delete=models.DO_NOTHING,
        related_name="favorites",
    )
    workshop = models.ForeignKey(
        Workshop,
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="favorited_by",
    )
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())

    class Meta:
        db_table = "favorite"
        managed = False
