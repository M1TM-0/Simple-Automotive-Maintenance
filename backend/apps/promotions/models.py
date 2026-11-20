from apps.core.db import CurrentTimestamp
from apps.core.fields import StoredImageField
from django.db import models


class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Percentual"
    FIXED = "fixed", "Valor fixo"


class PromotionStatus(models.TextChoices):
    ACTIVE = "active", "Ativa"
    INACTIVE = "inactive", "Inativa"
    EXPIRED = "expired", "Expirada"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    PAID = "paid", "Pago"
    FAILED = "failed", "Falhou"
    REFUNDED = "refunded", "Estornado"


class AdvertisementStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    ACTIVE = "active", "Ativa"
    COMPLETED = "completed", "Concluída"
    CANCELLED = "cancelled", "Cancelada"


class Promotion(models.Model):
    id_promotion = models.BigAutoField(primary_key=True)
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="promotions",
    )
    workshop_service = models.ForeignKey(
        "catalog.WorkshopService",
        db_column="id_workshop_service",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="promotions",
    )
    product = models.ForeignKey(
        "catalog.Product",
        db_column="id_product",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="promotions",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    type_discount = models.CharField(max_length=50, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    date_start = models.DateTimeField(db_default=CurrentTimestamp())
    date_end = models.DateTimeField()
    image_url = StoredImageField()
    status_promotion = models.CharField(
        max_length=50,
        choices=PromotionStatus.choices,
        db_default=PromotionStatus.ACTIVE.value,
    )

    def __str__(self):
        return self.title

    class Meta:
        db_table = "promotion"
        managed = False


class PromotionAdvertisement(models.Model):
    id_promotion_advertisement = models.BigAutoField(primary_key=True)
    promotion = models.ForeignKey(
        Promotion,
        db_column="id_promotion",
        on_delete=models.DO_NOTHING,
        related_name="advertisements",
    )
    image_url = StoredImageField(null=False, blank=False)
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()
    advertising_price = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(
        max_length=30,
        choices=PaymentStatus.choices,
        db_default=PaymentStatus.PENDING.value,
    )
    status_advertisement = models.CharField(
        max_length=30,
        choices=AdvertisementStatus.choices,
        db_default=AdvertisementStatus.PENDING.value,
    )

    def __str__(self):
        return f"Divulgação #{self.pk}"

    class Meta:
        db_table = "promotion_advertisement"
        managed = False


class PromotionEffective(models.Model):
    """Leitura de vw_promotion_effective: vigência real, nunca só o status persistido."""

    id_promotion = models.BigIntegerField(primary_key=True)
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    id_workshop_service = models.BigIntegerField(null=True)
    id_product = models.BigIntegerField(null=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True)
    type_discount = models.CharField(max_length=50)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()
    image_url = StoredImageField()
    status_promotion = models.CharField(max_length=50)
    effective_status = models.CharField(max_length=20)
    is_valid_now = models.BooleanField()

    class Meta:
        db_table = "vw_promotion_effective"
        managed = False


class AdvertisementEffective(models.Model):
    """Leitura de vw_advertisement_effective."""

    id_promotion_advertisement = models.BigIntegerField(primary_key=True)
    promotion = models.ForeignKey(
        Promotion,
        db_column="id_promotion",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    image_url = StoredImageField(null=False, blank=False)
    date_creation = models.DateTimeField()
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()
    advertising_price = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=30)
    status_advertisement = models.CharField(max_length=30)
    is_running_now = models.BooleanField()

    class Meta:
        db_table = "vw_advertisement_effective"
        managed = False
