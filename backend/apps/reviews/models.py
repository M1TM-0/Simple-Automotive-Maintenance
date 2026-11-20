import uuid

from apps.core.db import CurrentTimestamp
from django.db import models


class ReviewStatus(models.TextChoices):
    PUBLISHED = "published", "Publicada"
    HIDDEN = "hidden", "Oculta"
    UNDER_REVIEW = "under_review", "Em análise"


class DenunciationReason(models.TextChoices):
    INAPPROPRIATE_CONTENT = "inappropriate_content", "Conteúdo inapropriado"
    OFFENSIVE_LANGUAGE = "offensive_language", "Linguagem ofensiva"
    HARASSMENT = "harassment", "Assédio"
    SPAM = "spam", "Spam"
    FALSE_INFORMATION = "false_information", "Informação falsa"
    FRAUD = "fraud", "Fraude"
    OTHER = "other", "Outro"


class DenunciationStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    IN_REVIEW = "in_review", "Em análise"
    UPHELD = "upheld", "Procedente"
    DISMISSED = "dismissed", "Improcedente"


class Review(models.Model):
    id_review = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.OneToOneField(
        "attendances.Budget",
        db_column="id_budget",
        on_delete=models.DO_NOTHING,
        related_name="review",
    )
    rating = models.IntegerField()
    comment = models.TextField(null=True, blank=True)
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())
    workshop_response = models.TextField(null=True, blank=True)
    date_response = models.DateTimeField(null=True, blank=True)
    status_review = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        db_default=ReviewStatus.PUBLISHED.value,
    )

    class Meta:
        db_table = "review"
        managed = False


class Denunciation(models.Model):
    id_denunciation = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(
        "accounts.Client",
        db_column="id_client",
        on_delete=models.DO_NOTHING,
        related_name="denunciations",
    )
    review = models.ForeignKey(
        Review,
        db_column="id_review",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="denunciations",
    )
    promotion = models.ForeignKey(
        "promotions.Promotion",
        db_column="id_promotion",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="denunciations",
    )
    advertisement = models.ForeignKey(
        "promotions.PromotionAdvertisement",
        db_column="id_promotion_advertisement",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="denunciations",
    )
    reason = models.CharField(max_length=50, choices=DenunciationReason.choices)
    description = models.TextField(null=True, blank=True)
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())
    status_denunciation = models.CharField(
        max_length=30,
        choices=DenunciationStatus.choices,
        db_default=DenunciationStatus.PENDING.value,
    )
    moderation_decision = models.TextField(null=True, blank=True)
    date_resolution = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "denunciation"
        managed = False
