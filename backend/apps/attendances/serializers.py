"""Atendimentos, orçamentos e itens (BE-045…BE-055).

Grafias do banco preservadas: atendimento `canceled`; orçamento `cancelled`.
`id_client`, `id_workshop`, `status_*` e `total_price` nunca são lidos do corpo.
"""

from decimal import Decimal

from apps.attendances.models import AttendanceStatus, BudgetItemType, ExecutionStatus
from apps.core import limits
from apps.core.fields import media_url
from apps.core.money import MAX_QUANTITY, MAX_UNIT_PRICE
from apps.core.serializers import OptionalTextField
from apps.vehicles.serializers import MAX_MILEAGE_KM, VehicleSerializer
from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

# ------------------------------------------------------------------ resumos


class WorkshopBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name_fantasy = serializers.CharField()
    phone_number = serializers.CharField(allow_null=True)
    photo_profile = serializers.SerializerMethodField()

    def get_photo_profile(self, obj) -> str | None:
        page = getattr(obj, "page", None)
        return media_url(
            page.photo_profile if page else None, self.context.get("request")
        )


class ClientBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.CharField()


class ClientContactSerializer(ClientBriefSerializer):
    phone_number = serializers.CharField(allow_null=True)


class VehicleBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    brand = serializers.CharField()
    model = serializers.CharField()
    plate = serializers.CharField()
    year_model = serializers.IntegerField()


class BudgetBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    status_budget = serializers.CharField()
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    date_validity = serializers.DateTimeField()


class BudgetItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    id_budget = serializers.IntegerField(source="budget_id", read_only=True)
    item_type = serializers.CharField(read_only=True)
    id_workshop_service = serializers.IntegerField(
        source="workshop_service_id", read_only=True, allow_null=True
    )
    id_product = serializers.IntegerField(
        source="product_id", read_only=True, allow_null=True
    )
    id_service_item = serializers.IntegerField(
        source="service_item_id", read_only=True, allow_null=True
    )
    description = serializers.CharField(read_only=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, read_only=True)
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    execution_status = serializers.CharField(read_only=True)
    executed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class BudgetSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    id_attendance = serializers.IntegerField(source="attendance_id", read_only=True)
    status_budget = serializers.CharField(read_only=True)
    date_creation = serializers.DateTimeField(read_only=True)
    date_validity = serializers.DateTimeField(read_only=True)
    date_response = serializers.DateTimeField(read_only=True, allow_null=True)
    observations = serializers.CharField(read_only=True, allow_null=True)
    total_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    items = BudgetItemSerializer(many=True, read_only=True)


class AttendanceStateSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    status_attendance = serializers.CharField()


class BudgetActionSerializer(BudgetSerializer):
    """Orçamento devolvido por aprovar/recusar/enviar, com o novo status do atendimento."""

    attendance = AttendanceStateSerializer(read_only=True)


class ReviewBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="pk")
    id_budget = serializers.IntegerField(source="budget_id")
    rating = serializers.IntegerField()
    comment = serializers.CharField(allow_null=True)
    date_creation = serializers.DateTimeField()
    workshop_response = serializers.CharField(allow_null=True)
    date_response = serializers.DateTimeField(allow_null=True)
    status_review = serializers.CharField()


def current_budget(attendance):
    """Orçamento vigente (pendente ou aprovado) mais recente, a partir do prefetch."""
    for budget in attendance.budgets.all():
        if budget.status_budget in ("pending", "approved"):
            return budget
    return None


def attendance_review(attendance):
    for budget in attendance.budgets.all():
        try:
            return budget.review
        except ObjectDoesNotExist:
            continue
    return None


# ------------------------------------------------------------- atendimentos


class _AttendanceBase(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    status_attendance = serializers.CharField()
    date_attendance = serializers.DateTimeField()
    mileage_km = serializers.IntegerField(allow_null=True)
    observations = serializers.CharField(allow_null=True)
    budget = serializers.SerializerMethodField(
        help_text="Orçamento vigente (pendente/aprovado) ou null."
    )

    def get_budget(self, obj) -> dict | None:
        budget = current_budget(obj)
        return BudgetBriefSerializer(budget).data if budget else None


class ClientAttendanceSerializer(_AttendanceBase):
    """Resumo da lista do cliente (T13)."""

    workshop = WorkshopBriefSerializer()
    vehicle = VehicleBriefSerializer()


class ClientAttendanceDetailSerializer(ClientAttendanceSerializer):
    """Detalhe do cliente (T14): todos os orçamentos com itens e a avaliação."""

    technical_notes = serializers.CharField(allow_null=True)
    vehicle = VehicleSerializer()
    budgets = BudgetSerializer(many=True)
    review = serializers.SerializerMethodField()

    def get_review(self, obj) -> dict | None:
        review = attendance_review(obj)
        return ReviewBriefSerializer(review).data if review else None


class WorkshopAttendanceSerializer(_AttendanceBase):
    """Quadro/lista da oficina (T18)."""

    client = ClientBriefSerializer()
    vehicle = VehicleBriefSerializer()
    total_price = serializers.SerializerMethodField()

    @extend_schema_field(
        serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    )
    def get_total_price(self, obj) -> Decimal | None:
        budget = current_budget(obj)
        return budget.total_price if budget else None


class WorkshopAttendanceDetailSerializer(WorkshopAttendanceSerializer):
    """Detalhe da oficina (T19): cliente com telefone, veículo completo e orçamentos."""

    technical_notes = serializers.CharField(allow_null=True)
    client = ClientContactSerializer()
    vehicle = VehicleSerializer()
    budgets = BudgetSerializer(many=True)
    review = serializers.SerializerMethodField()

    def get_review(self, obj) -> dict | None:
        review = attendance_review(obj)
        return ReviewBriefSerializer(review).data if review else None


# ------------------------------------------------------------------ entradas


class AttendanceCreateSerializer(serializers.Serializer):
    id_workshop = serializers.IntegerField(min_value=1)
    id_vehicle = serializers.IntegerField(min_value=1)
    mileage_km = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=MAX_MILEAGE_KM
    )
    observations = OptionalTextField(max_length=limits.OBSERVATIONS)


class WorkshopAttendanceUpdateSerializer(serializers.Serializer):
    """`PATCH /workshop/attendances/{id}/`. Observações da oficina vão para
    `technical_notes` (DP-13); `observations` é aceito como sinônimo porque o
    frontend envia esse nome — o texto do pedido do cliente nunca é sobrescrito."""

    mileage_km = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=MAX_MILEAGE_KM
    )
    technical_notes = OptionalTextField(max_length=limits.OBSERVATIONS)
    observations = OptionalTextField(max_length=limits.OBSERVATIONS, write_only=True)

    def validate(self, attrs):
        alias = attrs.pop("observations", serializers.empty)
        if "technical_notes" not in attrs and alias is not serializers.empty:
            attrs["technical_notes"] = alias
        return attrs


WORKSHOP_TRANSITIONS = (
    AttendanceStatus.IN_PROGRESS,
    AttendanceStatus.COMPLETED,
    AttendanceStatus.DELIVERED,
    AttendanceStatus.CANCELED,
)


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            (value, AttendanceStatus(value).label) for value in WORKSHOP_TRANSITIONS
        ],
        error_messages={
            "invalid_choice": "Status inválido para a oficina. Use in_progress, completed, "
            "delivered ou canceled (os passos do orçamento têm rotas próprias)."
        },
    )


class BudgetWriteSerializer(serializers.Serializer):
    date_validity = serializers.DateTimeField(required=False)
    observations = OptionalTextField(max_length=limits.BUDGET_OBSERVATIONS)

    def validate_date_validity(self, value):
        from django.utils import timezone

        if value <= timezone.now():
            raise serializers.ValidationError("A validade deve ser uma data futura.")
        return value


class BudgetItemWriteSerializer(serializers.Serializer):
    """Item do orçamento. Referências de catálogo são validadas no serviço (mesma oficina)."""

    item_type = serializers.ChoiceField(choices=BudgetItemType.choices)
    id_workshop_service = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    id_product = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    id_service_item = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )
    quantity = serializers.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=3,
        min_value=Decimal("0.001"),
        max_value=MAX_QUANTITY,
    )
    unit_price = serializers.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=MAX_UNIT_PRICE,
    )


class BudgetItemResponseSerializer(BudgetItemSerializer):
    """Item + orçamento com o `total_price` recalculado pelo banco (o frontend exibe este total)."""

    budget = BudgetBriefSerializer(read_only=True)


class ExecutionSerializer(serializers.Serializer):
    execution_status = serializers.ChoiceField(choices=ExecutionStatus.choices)


# ------------------------------------------------------ clientes da oficina


class AttendedVehicleSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    brand = serializers.CharField()
    model = serializers.CharField()
    plate = serializers.CharField()


class WorkshopClientSerializer(serializers.Serializer):
    """Cliente atendido (T26): só o nome e o resumo do vínculo com esta oficina (RN03)."""

    id = serializers.IntegerField(source="pk")
    name = serializers.CharField()
    attendance_count = serializers.IntegerField()
    last_attendance = serializers.DateTimeField()
    vehicles = AttendedVehicleSerializer(source="attended_vehicles", many=True)


class AttendanceMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    date_attendance = serializers.DateTimeField()
    status_attendance = serializers.CharField()


class WorkshopClientVehicleSerializer(AttendedVehicleSerializer):
    year_model = serializers.IntegerField()
    history_shared = serializers.BooleanField(
        help_text="O cliente autorizou a consulta do histórico."
    )
    attendances = AttendanceMiniSerializer(source="workshop_attendances", many=True)
