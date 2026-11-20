from rest_framework import serializers

from .fields import ImageURLField, StoredImageField


class SamModelSerializer(serializers.ModelSerializer):
    """Serializador base: sempre emite `id` e converte colunas de imagem em URL."""

    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        StoredImageField: ImageURLField,
    }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            "id": str(instance.pk) if not isinstance(instance.pk, int) else instance.pk,
            **data,
        }


class OptionalTextField(serializers.CharField):
    """Texto opcional: apara as pontas e grava vazio como NULL (colunas TEXT/VARCHAR anuláveis)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def run_validation(self, data=serializers.empty):
        # O CharField devolve "" para texto em branco sem passar por to_internal_value.
        return super().run_validation(data) or None


class DateOrDateTimeField(serializers.DateTimeField):
    """Aceita data-hora ISO-8601 ou só a data (`2026-03-10` → meio-dia no fuso do negócio)."""

    def to_internal_value(self, value):
        from datetime import date, datetime, time

        from django.utils import timezone

        if isinstance(value, str) and len(value.strip()) == 10:
            try:
                day = date.fromisoformat(value.strip())
            except ValueError:
                pass
            else:
                return timezone.make_aware(datetime.combine(day, time(12, 0)))
        return super().to_internal_value(value)
