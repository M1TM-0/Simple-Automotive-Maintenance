from apps.catalog.models import Product, WorkshopService
from apps.promotions.models import AdvertisementEffective, PromotionEffective
from django.db.models import (
    BooleanField,
    CharField,
    F,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce


def workshop_promotions(workshop_id: int):
    service_name = (
        WorkshopService.objects.filter(pk=OuterRef("id_workshop_service"))
        .annotate(label=Coalesce("name_local", "service__name"))
        .values("label")[:1]
    )
    product_name = Product.objects.filter(pk=OuterRef("id_product")).values("name")[:1]
    return (
        PromotionEffective.objects.filter(workshop_id=workshop_id)
        .annotate(target_name=Coalesce(Subquery(service_name), Subquery(product_name)))
        .order_by("-date_start", "-id_promotion")
    )


def promotion_advertisements(promotion_id: int):
    return AdvertisementEffective.objects.filter(promotion_id=promotion_id).order_by(
        "-date_creation", "-id_promotion_advertisement"
    )


# ------------------------------------------------- vitrine pública (BE-066, BE-068)

# Colunas comuns às duas metades do UNION (promoções e divulgações).
ON_AIR_COLUMNS = (
    "p_kind",
    "p_rank",
    "p_id",
    "p_promotion_id",
    "p_title",
    "p_description",
    "p_image",
    "p_workshop_id",
    "p_workshop_name",
    "p_target_name",
    "p_type_discount",
    "p_discount_value",
    "p_date_start",
    "p_date_end",
    "p_is_valid_now",
    "p_is_running_now",
)


def _project(queryset, columns):
    return queryset.annotate(**{name: columns[name] for name in ON_AIR_COLUMNS}).values(
        *ON_AIR_COLUMNS
    )


def on_air(workshop_id: int | None = None, *, include_advertisements: bool = True):
    """Promoções vigentes (`is_valid_now`) e divulgações em execução (`is_running_now`)
    de oficinas públicas (DP-20). A vigência vem das views do banco, nunca do status.

    Ordem: divulgações primeiro (espaço pago), depois promoções que terminam antes.
    Uma promoção com divulgação no ar aparece duas vezes (`kind` diferente, `id` da
    divulgação no segundo item — é o alvo de denúncia `advertisement`).
    """
    from apps.workshops.selectors import public_workshop_ids

    promotions = PromotionEffective.objects.filter(
        is_valid_now=True, workshop_id__in=public_workshop_ids()
    )
    if workshop_id is not None:
        promotions = promotions.filter(workshop_id=workshop_id)

    service_name = (
        WorkshopService.objects.filter(pk=OuterRef("id_workshop_service"))
        .annotate(label=Coalesce("name_local", "service__name"))
        .values("label")[:1]
    )
    product_name = Product.objects.filter(pk=OuterRef("id_product")).values("name")[:1]
    promotion_rows = _project(
        promotions,
        {
            "p_kind": Value("promotion", output_field=CharField()),
            "p_rank": Value(1, output_field=IntegerField()),
            "p_id": F("pk"),
            "p_promotion_id": F("pk"),
            "p_title": F("title"),
            "p_description": F("description"),
            "p_image": F("image_url"),
            "p_workshop_id": F("workshop_id"),
            "p_workshop_name": F("workshop__name_fantasy"),
            "p_target_name": Coalesce(Subquery(service_name), Subquery(product_name)),
            "p_type_discount": F("type_discount"),
            "p_discount_value": F("discount_value"),
            "p_date_start": F("date_start"),
            "p_date_end": F("date_end"),
            "p_is_valid_now": F("is_valid_now"),
            "p_is_running_now": Value(None, output_field=BooleanField()),
        },
    )
    if not include_advertisements:
        return promotion_rows.order_by("p_date_end", "p_id")

    advertisements = AdvertisementEffective.objects.filter(
        is_running_now=True, promotion__workshop_id__in=public_workshop_ids()
    )
    if workshop_id is not None:
        advertisements = advertisements.filter(promotion__workshop_id=workshop_id)
    advertisement_rows = _project(
        advertisements,
        {
            "p_kind": Value("advertisement", output_field=CharField()),
            "p_rank": Value(0, output_field=IntegerField()),
            "p_id": F("pk"),
            "p_promotion_id": F("promotion_id"),
            "p_title": F("promotion__title"),
            "p_description": F("promotion__description"),
            "p_image": F("image_url"),
            "p_workshop_id": F("promotion__workshop_id"),
            "p_workshop_name": F("promotion__workshop__name_fantasy"),
            "p_target_name": Coalesce(
                "promotion__workshop_service__name_local",
                "promotion__workshop_service__service__name",
                "promotion__product__name",
            ),
            "p_type_discount": F("promotion__type_discount"),
            "p_discount_value": F("promotion__discount_value"),
            "p_date_start": F("promotion__date_start"),
            "p_date_end": F("promotion__date_end"),
            # Divulgação só roda com a promoção vigente (vw_advertisement_effective).
            "p_is_valid_now": Value(True, output_field=BooleanField()),
            "p_is_running_now": F("is_running_now"),
        },
    )
    return advertisement_rows.union(promotion_rows, all=True).order_by(
        "p_rank", "p_date_end", "p_id"
    )
