"""Veículos do cliente (BE-043) e histórico de manutenção (BE-044, BE-056)."""

from datetime import datetime

from apps.core import limits
from apps.core.fields import ImageURLField
from apps.core.serializers import DateOrDateTimeField, OptionalTextField
from apps.core.timeutils import business_now, to_business_time
from apps.core.validators import clean_service_name, validate_plate
from apps.vehicles.models import Exchange, Fuel
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

MIN_YEAR = 1900
MAX_MILEAGE_KM = 5_000_000
PHOTO_FIELDS = ("photo_1", "photo_2", "photo_3")


class VehicleSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    brand = serializers.CharField(read_only=True)
    model = serializers.CharField(read_only=True)
    year_fabrication = serializers.IntegerField(read_only=True)
    year_model = serializers.IntegerField(read_only=True)
    plate = serializers.CharField(read_only=True)
    fuel = serializers.CharField(read_only=True)
    exchange = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True, allow_null=True)
    motorization = serializers.CharField(read_only=True, allow_null=True)
    color = serializers.CharField(read_only=True, allow_null=True)
    information = serializers.CharField(read_only=True, allow_null=True)
    photo_1 = ImageURLField(read_only=True)
    photo_2 = ImageURLField(read_only=True)
    photo_3 = ImageURLField(read_only=True)
    mileage_km = serializers.IntegerField(read_only=True, allow_null=True)
    history_shared = serializers.BooleanField(read_only=True)


class VehicleWriteSerializer(serializers.Serializer):
    """Cadastro/edição (multipart ou JSON). Fotos por posição fixa: `photo_2=""` limpa só ela.

    `id_client` nunca vem do corpo (é o cliente da sessão).
    """

    brand = serializers.CharField(max_length=255)
    model = serializers.CharField(max_length=255)
    year_fabrication = serializers.IntegerField()
    year_model = serializers.IntegerField()
    plate = serializers.CharField(max_length=10)
    fuel = serializers.ChoiceField(choices=Fuel.choices)
    exchange = serializers.ChoiceField(choices=Exchange.choices)
    version = OptionalTextField(max_length=255)
    motorization = OptionalTextField(max_length=255)
    color = OptionalTextField(max_length=20)
    information = OptionalTextField(max_length=limits.VEHICLE_INFORMATION)
    photo_1 = ImageURLField(required=False)
    photo_2 = ImageURLField(required=False)
    photo_3 = ImageURLField(required=False)
    mileage_km = serializers.IntegerField(min_value=0, max_value=MAX_MILEAGE_KM)
    # `default`: booleano ausente em multipart não pode virar False numa edição parcial.
    history_shared = serializers.BooleanField(required=False, default=False)

    @staticmethod
    def _year(value):
        last = business_now().year + 1
        if not MIN_YEAR <= value <= last:
            raise serializers.ValidationError(
                f"Informe um ano entre {MIN_YEAR} e {last}."
            )
        return value

    def validate_year_fabrication(self, value):
        return self._year(value)

    def validate_year_model(self, value):
        return self._year(value)

    def validate_plate(self, value):
        try:
            return validate_plate(value)
        except DjangoValidationError:
            raise serializers.ValidationError(
                "Placa inválida. Use o formato antigo (ABC1234) ou Mercosul (ABC1D23)."
            ) from None

    def validate(self, attrs):
        for field in ("brand", "model"):
            if field in attrs:
                attrs[field] = attrs[field].strip()
                if not attrs[field]:
                    raise serializers.ValidationError(
                        {field: ["Este campo não pode ficar em branco."]}
                    )
        return attrs


# ------------------------------------------------------------------ histórico


class MaintenanceHistorySerializer(serializers.Serializer):
    """Linha de `vw_vehicle_maintenance_history` (serviços e peças). Mesma forma para
    o cliente (BE-044) e para a oficina autorizada (BE-056)."""

    id = serializers.SerializerMethodField(
        help_text="`<record_type>-<id_record>` (serviço e peça têm sequências próprias)."
    )
    record_type = serializers.CharField(help_text="`service` ou `part`.")
    id_record = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, allow_null=True
    )
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    brand = serializers.CharField(allow_null=True)
    category = serializers.CharField(allow_null=True)
    date_maintenance = serializers.DateTimeField()
    mileage_km = serializers.IntegerField(allow_null=True)
    observations = serializers.CharField(allow_null=True)
    interval_km = serializers.IntegerField(allow_null=True)
    id_attendance = serializers.IntegerField(allow_null=True)
    id_service = serializers.IntegerField(allow_null=True)
    id_product = serializers.IntegerField(allow_null=True)
    id_workshop = serializers.IntegerField(allow_null=True)
    workshop_name = serializers.CharField(allow_null=True)

    def get_id(self, obj) -> str:
        return f"{obj.record_type}-{obj.id_record}"


class ManualMaintenanceSerializer(serializers.Serializer):
    """`POST /vehicles/{id}/history/`: registro manual (o histórico só cresce)."""

    service_name = serializers.CharField(max_length=255)
    id_service = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    date_maintenance = DateOrDateTimeField()
    mileage_km = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=MAX_MILEAGE_KM
    )
    observations = OptionalTextField(max_length=limits.HISTORY_OBSERVATIONS)
    interval_km = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=MAX_MILEAGE_KM
    )

    def validate_service_name(self, value):
        name = clean_service_name(value)
        if not name:
            raise serializers.ValidationError("Informe o serviço realizado.")
        return name

    def validate_id_service(self, value):
        from apps.catalog.models import Service

        if value is not None and not Service.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Serviço inexistente.")
        return value

    def validate_date_maintenance(self, value):
        # Compara por dia no fuso do negócio: o frontend envia a data escolhida ao meio-dia.
        if to_business_time(value).date() > business_now().date():
            raise serializers.ValidationError(
                "A data da manutenção não pode ser futura."
            )
        return value


# ------------------------------------------------------ manutenção preventiva


class UpcomingMaintenanceSerializer(serializers.Serializer):
    """Próxima manutenção de um item (BE-077); calculada por `apps/vehicles/reminders.py`."""

    id = serializers.SerializerMethodField(
        help_text="Registro da última execução (`service-<id>`), como no histórico."
    )
    id_service = serializers.IntegerField(source="service_id", allow_null=True)
    service_name = serializers.CharField(help_text="Nome da última execução.")
    last_date = serializers.DateTimeField()
    last_mileage_km = serializers.IntegerField()
    interval_km = serializers.IntegerField(
        help_text="Intervalo mais recente informado para o item."
    )
    next_mileage_km = serializers.IntegerField(
        help_text="km da última execução + intervalo."
    )
    current_mileage_km = serializers.IntegerField()
    remaining_km = serializers.IntegerField(help_text="Negativo quando vencida.")
    progress_percent = serializers.IntegerField(min_value=0, max_value=100)
    status = serializers.ChoiceField(
        choices=(("ok", "Em dia"), ("soon", "Próxima"), ("overdue", "Vencida")),
        help_text="`soon` quando faltar até `SAM_MAINTENANCE_REMINDER_PERCENT` % do intervalo.",
    )
    reminder_sent_at = serializers.SerializerMethodField(
        help_text="Quando o cliente foi avisado neste ciclo."
    )

    def get_id(self, obj) -> str:
        return f"service-{obj.last_record_id}"

    def get_reminder_sent_at(self, obj) -> datetime | None:
        sent = self.context.get("reminders", {}).get(obj.last_record_id)
        return serializers.DateTimeField().to_representation(sent) if sent else None
