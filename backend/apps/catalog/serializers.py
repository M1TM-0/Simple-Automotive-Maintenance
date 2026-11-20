"""Catálogo global (BE-036), serviços da oficina (BE-041) e produtos (BE-042)."""

from decimal import Decimal

from apps.catalog.models import Service, ServiceCategory
from apps.core import limits
from apps.core.fields import ImageURLField
from apps.core.money import MAX_UNIT_PRICE
from apps.core.serializers import OptionalTextField
from apps.core.validators import clean_service_name
from rest_framework import serializers

MAX_DURATION_MINUTES = 100_000


def money_field(**kwargs):
    kwargs.setdefault("max_digits", 10)
    kwargs.setdefault("decimal_places", 2)
    kwargs.setdefault("min_value", Decimal("0.00"))
    kwargs.setdefault("max_value", MAX_UNIT_PRICE)
    return serializers.DecimalField(**kwargs)


# ------------------------------------------------------------- catálogo global


class ServiceCategorySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="pk", read_only=True)

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "description")


class ServiceSerializer(serializers.ModelSerializer):
    """Serviço ativo do catálogo global (contrato §8.2)."""

    id = serializers.IntegerField(source="pk", read_only=True)
    id_service_category = serializers.IntegerField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Service
        fields = ("id", "name", "description", "id_service_category", "category_name")


# ------------------------------------------------------- serviços da oficina


class WorkshopServiceSerializer(serializers.Serializer):
    """Serviço do catálogo da oficina: global (`id_service`) ou personalizado (`name_local`).

    Nome, descrição e categoria vêm do serviço global quando houver; senão, do
    nome local e da categoria sugerida. `status_solicitation`/`motivation_rejection`
    mostram o andamento da solicitação de inclusão no catálogo global.
    """

    id = serializers.IntegerField(source="pk", read_only=True)
    id_service = serializers.IntegerField(
        source="service_id", read_only=True, allow_null=True
    )
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    name_local = serializers.CharField(read_only=True, allow_null=True)
    description_local = serializers.CharField(read_only=True, allow_null=True)
    id_service_category = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    id_suggested_category = serializers.IntegerField(
        source="suggested_category_id", read_only=True, allow_null=True
    )
    price_base = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    duration_estimate = serializers.IntegerField(read_only=True)
    disponibility = serializers.BooleanField(read_only=True)
    status_solicitation = serializers.CharField(read_only=True, allow_null=True)
    motivation_rejection = serializers.CharField(read_only=True, allow_null=True)
    date_solicitation_response = serializers.DateTimeField(
        read_only=True, allow_null=True
    )

    def get_name(self, obj) -> str:
        # Personalizado (mesmo depois de aprovado) mantém o nome dado pela oficina.
        return obj.name_local or obj.service.name

    def get_description(self, obj) -> str | None:
        if obj.description_local:
            return obj.description_local
        return obj.service.description if obj.service_id else None

    def get_id_service_category(self, obj) -> int | None:
        if obj.service_id:
            return obj.service.category_id
        return obj.suggested_category_id

    def get_category_name(self, obj) -> str | None:
        if obj.service_id:
            return obj.service.category.name
        return obj.suggested_category.name if obj.suggested_category_id else None


class WorkshopServiceCreateSerializer(serializers.Serializer):
    """`POST /workshop/services/`: catálogo `{id_service,…}` ou personalizado `{name_local,…}`.

    Campos de estado (`status_solicitation`, `motivation_rejection`, `id_workshop`)
    não existem aqui: vindos do corpo são ignorados.
    """

    id_service = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    name_local = serializers.CharField(required=False, allow_blank=True, max_length=255)
    description_local = OptionalTextField(max_length=limits.DESCRIPTION)
    id_suggested_category = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    price_base = money_field()
    duration_estimate = serializers.IntegerField(
        min_value=1, max_value=MAX_DURATION_MINUTES
    )
    disponibility = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        service_id = attrs.get("id_service")
        name = clean_service_name(attrs.get("name_local") or "")

        if service_id is not None:
            if name or attrs.get("id_suggested_category"):
                raise serializers.ValidationError(
                    {
                        "id_service": [
                            "Escolha um serviço do catálogo ou informe um serviço personalizado, não os dois."
                        ]
                    }
                )
            service = Service.objects.filter(pk=service_id, active=True).first()
            if service is None:
                raise serializers.ValidationError(
                    {"id_service": ["Serviço inexistente ou indisponível."]}
                )
            attrs["service"] = service
            attrs.pop("name_local", None)
            return attrs

        if not name:
            raise serializers.ValidationError(
                {
                    "name_local": [
                        "Informe o nome do serviço ou escolha um serviço do catálogo."
                    ]
                }
            )
        category_id = attrs.get("id_suggested_category")
        if category_id is None:
            raise serializers.ValidationError(
                {"id_suggested_category": ["Escolha uma categoria."]}
            )
        category = ServiceCategory.objects.filter(pk=category_id).first()
        if category is None:
            raise serializers.ValidationError(
                {"id_suggested_category": ["Categoria inexistente."]}
            )

        attrs["service"] = None
        attrs["name_local"] = name
        attrs["suggested_category"] = category
        return attrs


class WorkshopServiceUpdateSerializer(serializers.Serializer):
    """`PATCH /workshop/services/{id}/`: nome e origem são imutáveis (sem DELETE)."""

    description_local = OptionalTextField(max_length=limits.DESCRIPTION)
    price_base = money_field(required=False)
    duration_estimate = serializers.IntegerField(
        required=False, min_value=1, max_value=MAX_DURATION_MINUTES
    )
    disponibility = serializers.BooleanField(required=False)


# ------------------------------------------------------------------- produtos


class ProductSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_null=True)
    category = serializers.CharField(read_only=True, allow_null=True)
    brand = serializers.CharField(read_only=True, allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    disponibility = serializers.BooleanField(read_only=True)
    active = serializers.BooleanField(read_only=True)
    photo = ImageURLField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ProductWriteSerializer(serializers.Serializer):
    """Cadastro/edição (multipart; booleanos `true`/`false`). `photo=""` remove a foto."""

    name = serializers.CharField(max_length=255)
    description = OptionalTextField(max_length=limits.DESCRIPTION)
    category = OptionalTextField(max_length=255)
    brand = OptionalTextField(max_length=255)
    price = money_field()
    # `default`: em multipart o DRF trata booleano ausente como False; aqui ausente = True.
    disponibility = serializers.BooleanField(required=False, default=True)
    active = serializers.BooleanField(required=False, default=True)
    photo = ImageURLField(required=False)


class PublicProductSerializer(serializers.Serializer):
    """Produto no catálogo informativo público (RN10: sem carrinho; só `active`)."""

    id = serializers.IntegerField(source="pk", read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_null=True)
    category = serializers.CharField(read_only=True, allow_null=True)
    brand = serializers.CharField(read_only=True, allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    disponibility = serializers.BooleanField(read_only=True)
    photo = ImageURLField(read_only=True)
