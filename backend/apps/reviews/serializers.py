"""Avaliações (BE-059, BE-060) e denúncias (BE-061)."""

from apps.core import limits
from apps.core.serializers import OptionalTextField
from apps.reviews.domain import author_display_name
from apps.reviews.models import DenunciationReason
from rest_framework import serializers

TARGET_TYPES = (
    ("review", "Avaliação"),
    ("promotion", "Promoção"),
    ("advertisement", "Divulgação"),
)


class ReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    id_budget = serializers.IntegerField(source="budget_id", read_only=True)
    id_attendance = serializers.IntegerField(
        source="budget.attendance_id", read_only=True
    )
    rating = serializers.IntegerField(read_only=True)
    comment = serializers.CharField(read_only=True, allow_null=True)
    date_creation = serializers.DateTimeField(read_only=True)
    workshop_response = serializers.CharField(read_only=True, allow_null=True)
    date_response = serializers.DateTimeField(read_only=True, allow_null=True)
    status_review = serializers.CharField(read_only=True)


class WorkshopReviewSerializer(ReviewSerializer):
    client_name = serializers.SerializerMethodField(
        help_text="Primeiro nome + inicial (DP-15)."
    )

    def get_client_name(self, obj) -> str | None:
        return author_display_name(obj.budget.attendance.client.name)


class PublicReviewSerializer(serializers.Serializer):
    """Avaliação publicada no perfil (BE-066): sem orçamento, atendimento nem status."""

    id = serializers.UUIDField(source="pk", read_only=True)
    rating = serializers.IntegerField(read_only=True)
    comment = serializers.CharField(read_only=True, allow_null=True)
    date_creation = serializers.DateTimeField(read_only=True)
    workshop_response = serializers.CharField(read_only=True, allow_null=True)
    date_response = serializers.DateTimeField(read_only=True, allow_null=True)
    client_name = serializers.SerializerMethodField(
        help_text="Primeiro nome + inicial (DP-15)."
    )

    def get_client_name(self, obj) -> str | None:
        return author_display_name(obj.budget.attendance.client.name)


class ReviewCreateSerializer(serializers.Serializer):
    id_budget = serializers.IntegerField(min_value=1)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = OptionalTextField(max_length=limits.REVIEW_COMMENT)


class ReviewResponseSerializer(serializers.Serializer):
    workshop_response = serializers.CharField(max_length=limits.REVIEW_RESPONSE)


class DenunciationCreateSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=TARGET_TYPES)
    target_id = serializers.CharField(max_length=64)
    reason = serializers.ChoiceField(choices=DenunciationReason.choices)
    description = OptionalTextField(max_length=limits.DENUNCIATION_DESCRIPTION)

    def validate(self, attrs):
        if attrs["reason"] == DenunciationReason.OTHER and not attrs.get("description"):
            raise serializers.ValidationError(
                {"description": ["Descreva o motivo da denúncia."]}
            )
        return attrs


class DenunciationSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    reason = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    status_denunciation = serializers.CharField()
    date_creation = serializers.DateTimeField()

    def get_target_type(self, obj) -> str:
        if obj.review_id:
            return "review"
        return "promotion" if obj.promotion_id else "advertisement"

    def get_target_id(self, obj) -> str:
        return str(obj.review_id or obj.promotion_id or obj.advertisement_id)
