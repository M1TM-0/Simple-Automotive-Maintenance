"""Formas das rotas `/api/admin/*` (BE-073, BE-074; contrato §8.10).

O admin vê o nome completo de quem denunciou e de quem avaliou (o público só vê a
forma abreviada, DP-15); e-mail, CNPJ e senha não saem por aqui.
"""

from apps.catalog.serializers import WorkshopServiceSerializer
from apps.core import limits
from apps.core.serializers import OptionalTextField
from apps.core.validators import clean_service_name
from apps.reviews.models import DenunciationStatus
from apps.reviews.serializers import DenunciationSerializer, ReviewSerializer
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

WorkshopRef = inline_serializer(
    "AdminWorkshopRef",
    {"id": serializers.IntegerField(), "name_fantasy": serializers.CharField()},
)

DenouncedContent = inline_serializer(
    "AdminDenouncedContent",
    {
        "type": serializers.ChoiceField(
            choices=("review", "promotion", "advertisement")
        ),
        "id": serializers.CharField(),
        "status": serializers.CharField(
            help_text="status_review | status_promotion | status_advertisement"
        ),
        "workshop": WorkshopRef,
        "rating": serializers.IntegerField(required=False, help_text="Só avaliação."),
        "comment": serializers.CharField(
            required=False, allow_null=True, help_text="Só avaliação."
        ),
        "author_name": serializers.CharField(required=False, help_text="Só avaliação."),
        "title": serializers.CharField(
            required=False, help_text="Promoção ou divulgação."
        ),
        "id_promotion": serializers.IntegerField(
            required=False, help_text="Só divulgação."
        ),
        "payment_status": serializers.CharField(
            required=False, help_text="Só divulgação."
        ),
    },
)


def _workshop(workshop) -> dict:
    return {"id": workshop.pk, "name_fantasy": workshop.name_fantasy}


# ----------------------------------------------------------------- denúncias


class AdminDenunciationSerializer(DenunciationSerializer):
    """Item da fila: a denúncia, quem denunciou e um resumo do conteúdo denunciado."""

    moderation_decision = serializers.CharField(allow_null=True)
    date_resolution = serializers.DateTimeField(allow_null=True)
    reporter = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()

    @extend_schema_field(
        inline_serializer(
            "AdminReporter",
            {"id": serializers.IntegerField(), "name": serializers.CharField()},
        )
    )
    def get_reporter(self, obj):
        return {"id": obj.client_id, "name": obj.client.name}

    @extend_schema_field(DenouncedContent)
    def get_content(self, obj):
        if obj.review_id:
            review = obj.review
            return {
                "type": "review",
                "id": str(review.pk),
                "status": review.status_review,
                "workshop": _workshop(review.budget.workshop),
                "rating": review.rating,
                "comment": review.comment,
                "author_name": review.budget.attendance.client.name,
            }
        if obj.promotion_id:
            promotion = obj.promotion
            return {
                "type": "promotion",
                "id": str(promotion.pk),
                "status": promotion.status_promotion,
                "workshop": _workshop(promotion.workshop),
                "title": promotion.title,
            }
        advertisement = obj.advertisement
        return {
            "type": "advertisement",
            "id": str(advertisement.pk),
            "status": advertisement.status_advertisement,
            "workshop": _workshop(advertisement.promotion.workshop),
            "title": advertisement.promotion.title,
            "id_promotion": advertisement.promotion_id,
            "payment_status": advertisement.payment_status,
        }


MODERATION_TARGETS = (
    (DenunciationStatus.IN_REVIEW.value, "Em análise"),
    (DenunciationStatus.UPHELD.value, "Procedente"),
    (DenunciationStatus.DISMISSED.value, "Improcedente"),
)


class DenunciationModerationSerializer(serializers.Serializer):
    """`in_review` (decisão opcional, como nota) ou resolução com decisão obrigatória."""

    status_denunciation = serializers.ChoiceField(choices=MODERATION_TARGETS)
    moderation_decision = OptionalTextField(max_length=limits.MODERATION_DECISION)

    def validate(self, attrs):
        resolving = attrs["status_denunciation"] != DenunciationStatus.IN_REVIEW
        if resolving and not attrs.get("moderation_decision"):
            raise serializers.ValidationError(
                {
                    "moderation_decision": [
                        "Informe a decisão da moderação para resolver a denúncia."
                    ]
                }
            )
        return attrs


class AdminReviewSerializer(ReviewSerializer):
    workshop = serializers.SerializerMethodField()
    client_name = serializers.CharField(
        source="budget.attendance.client.name", read_only=True
    )

    @extend_schema_field(WorkshopRef)
    def get_workshop(self, obj):
        return _workshop(obj.budget.workshop)


# ------------------------------------------------------ serviços personalizados


class ServiceRequestSerializer(WorkshopServiceSerializer):
    """Solicitação = serviço personalizado da oficina (contrato §8.10) + a oficina."""

    workshop = serializers.SerializerMethodField()
    suggested_category_name = serializers.CharField(
        source="suggested_category.name", read_only=True, allow_null=True, default=None
    )
    service_name = serializers.CharField(
        source="service.name", read_only=True, allow_null=True, default=None
    )
    created_at = serializers.DateTimeField(read_only=True)

    @extend_schema_field(WorkshopRef)
    def get_workshop(self, obj):
        return _workshop(obj.workshop)


class ServiceRequestApproveSerializer(serializers.Serializer):
    """Tudo opcional: valem só quando um serviço global novo é criado (o existente é
    reaproveitado sem alteração)."""

    id_category = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    description = OptionalTextField(max_length=limits.DESCRIPTION)

    def validate_id_category(self, value):
        from apps.catalog.models import ServiceCategory

        if value is not None and not ServiceCategory.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Categoria inexistente.")
        return value

    def validate_name(self, value):
        return clean_service_name(value or "") or None


class ServiceRequestRejectSerializer(serializers.Serializer):
    motivation = serializers.CharField(max_length=limits.REJECTION_MOTIVATION)
