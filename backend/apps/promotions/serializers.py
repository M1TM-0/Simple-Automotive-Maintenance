"""Promoções (BE-063) e divulgações pagas (BE-064).

A leitura vem sempre das views `vw_promotion_effective`/`vw_advertisement_effective`
(vigência real), nunca só do status persistido. Upload em `image`; a resposta
devolve `image_url`.
"""

from decimal import Decimal

from apps.core import limits
from apps.core.fields import ImageURLField
from apps.core.money import MAX_UNIT_PRICE
from apps.core.serializers import OptionalTextField
from apps.promotions.models import DiscountType, PromotionStatus
from rest_framework import serializers


class PromotionSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    title = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    id_workshop_service = serializers.IntegerField(allow_null=True)
    id_product = serializers.IntegerField(allow_null=True)
    target_name = serializers.CharField(
        allow_null=True, help_text="Nome do serviço ou produto em promoção."
    )
    type_discount = serializers.CharField()
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    date_start = serializers.DateTimeField()
    date_end = serializers.DateTimeField()
    image_url = ImageURLField(read_only=True)
    status_promotion = serializers.CharField(
        help_text="Estado persistido (active/inactive/expired)."
    )
    effective_status = serializers.CharField(
        help_text="active/scheduled/inactive/expired, pela data atual."
    )
    is_valid_now = serializers.BooleanField()


class PromotionWriteSerializer(serializers.Serializer):
    """Multipart: `id_workshop_service`/`id_product` vazios = sem alvo; `image=""` remove."""

    title = serializers.CharField(max_length=255)
    description = OptionalTextField(max_length=limits.DESCRIPTION)
    id_workshop_service = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    id_product = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    type_discount = serializers.ChoiceField(choices=DiscountType.choices)
    discount_value = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        max_value=MAX_UNIT_PRICE,
    )
    date_start = serializers.DateTimeField(required=False)
    date_end = serializers.DateTimeField()
    status_promotion = serializers.ChoiceField(
        choices=[
            (PromotionStatus.ACTIVE, "Ativa"),
            (PromotionStatus.INACTIVE, "Inativa"),
        ],
        required=False,
        default=PromotionStatus.ACTIVE,
    )
    image = ImageURLField(required=False)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe o título da promoção.")
        return value


class AdvertisementSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    id_promotion = serializers.IntegerField(source="promotion_id")
    image_url = ImageURLField(read_only=True)
    date_creation = serializers.DateTimeField()
    date_start = serializers.DateTimeField()
    date_end = serializers.DateTimeField()
    advertising_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_status = serializers.CharField()
    status_advertisement = serializers.CharField()
    is_running_now = serializers.BooleanField(
        help_text="No ar agora (ativa, paga, no período e com a promoção vigente)."
    )


class AdvertisementCreateSerializer(serializers.Serializer):
    image = ImageURLField(required=True, allow_null=False)
    date_start = serializers.DateTimeField()
    date_end = serializers.DateTimeField()

    def validate_image(self, value):
        if value is None:
            raise serializers.ValidationError("Envie a imagem da divulgação.")
        return value


class WorkshopRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name_fantasy = serializers.CharField()


class PublicPromotionSerializer(serializers.Serializer):
    """Item de `GET /promotions/` e `GET /workshops/{id}/promotions/` (linha `p_*` do UNION).

    `kind=promotion`: `id` = promoção, `is_running_now = null` (só faz sentido em
    divulgação). `kind=advertisement`: `id` = divulgação (alvo de denúncia),
    `image_url` = imagem da divulgação, `id_promotion` = promoção divulgada.
    `date_start`/`date_end` são sempre a vigência do desconto (da promoção).
    """

    id = serializers.IntegerField()
    kind = serializers.ChoiceField(
        choices=[("promotion", "Promoção"), ("advertisement", "Divulgação")]
    )
    id_promotion = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    image_url = serializers.CharField(allow_null=True)
    workshop = WorkshopRefSerializer()
    target_name = serializers.CharField(allow_null=True)
    type_discount = serializers.CharField()
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    date_start = serializers.DateTimeField()
    date_end = serializers.DateTimeField()
    is_valid_now = serializers.BooleanField()
    is_running_now = serializers.BooleanField(allow_null=True)

    def to_representation(self, row):
        from apps.core.fields import media_url

        date_field = serializers.DateTimeField()
        return {
            "id": row["p_id"],
            "kind": row["p_kind"],
            "id_promotion": row["p_promotion_id"],
            "title": row["p_title"],
            "description": row["p_description"],
            "image_url": media_url(row["p_image"], self.context.get("request")),
            "workshop": {
                "id": row["p_workshop_id"],
                "name_fantasy": row["p_workshop_name"],
            },
            "target_name": row["p_target_name"],
            "type_discount": row["p_type_discount"],
            "discount_value": f"{row['p_discount_value']:.2f}",
            "date_start": date_field.to_representation(row["p_date_start"]),
            "date_end": date_field.to_representation(row["p_date_end"]),
            "is_valid_now": row["p_is_valid_now"],
            "is_running_now": row["p_is_running_now"],
        }
