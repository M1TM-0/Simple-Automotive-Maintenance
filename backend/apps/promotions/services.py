"""Casos de uso de promoções e divulgações (BE-063, BE-064, BE-076).

O banco valida percentual ≤ 100, datas, alvo XOR, ativação só antes do fim e
imutabilidade da promoção expirada. Aqui as mesmas condições são checadas antes,
por campo, para devolver 400 (validação) em vez de 409 (estado).

**Pagamento e ativação das divulgações (BE-076, DP-09).** O admin confirma o
pagamento à mão (Django Admin, sem gateway); a divulgação paga entra no ar quando
o período começa — na hora da confirmação, se já começou, ou pela rotina `jobs`
(`run_expiration_jobs`). Divulgação paga que acaba `cancelled` (promoção
desativada ou expirada antes de ir ao ar, moderação, admin) tem o pagamento
marcado `refunded` — "marcado para estorno": o admin devolve o valor por fora,
como recebeu. A trigger do banco não mexe em `payment_status`.

**Bloqueios.** A promoção é travada com `FOR NO KEY UPDATE` (`no_key=True`), não
`FOR UPDATE`: a trigger da divulgação pega `FOR KEY SHARE` na promoção depois de
travar a própria linha; com `FOR UPDATE` a desativação da promoção e a ativação
pela rotina se travariam em ordem inversa (deadlock).
"""

import math
from decimal import ROUND_HALF_UP, Decimal

from apps.catalog.models import Product, WorkshopService
from apps.core.db import CurrentTimestamp
from apps.core.exceptions import ApiConflict, ApiValidationFailure
from apps.core.money import MONEY_PLACES
from apps.core.storage import apply_image_changes, delete_stored_image, save_image
from apps.core.transactions import transactional
from apps.notifications import events
from apps.promotions.models import (
    AdvertisementStatus,
    DiscountType,
    PaymentStatus,
    Promotion,
    PromotionAdvertisement,
    PromotionEffective,
    PromotionStatus,
)
from django.conf import settings
from django.db import transaction
from django.utils import timezone

PROMOTION_FIELDS = (
    "title",
    "description",
    "type_discount",
    "discount_value",
    "date_start",
    "date_end",
    "status_promotion",
)
EXPIRED_IS_FINAL = "Uma promoção expirada é definitiva: crie uma nova promoção."
PERIOD_OUTSIDE = "O período da divulgação deve estar contido no período da promoção."


def _validate_promotion(workshop_id: int, values: dict) -> None:
    errors = {}
    service_id, product_id = values.get("workshop_service_id"), values.get("product_id")
    if service_id is not None and product_id is not None:
        errors["id_workshop_service"] = [
            "Escolha um serviço OU um produto (não os dois)."
        ]
    elif (
        service_id is not None
        and not WorkshopService.objects.filter(
            pk=service_id, workshop_id=workshop_id
        ).exists()
    ):
        errors["id_workshop_service"] = ["Escolha um serviço da sua oficina."]
    elif (
        product_id is not None
        and not Product.objects.filter(pk=product_id, workshop_id=workshop_id).exists()
    ):
        errors["id_product"] = ["Escolha um produto da sua oficina."]

    if (
        values["type_discount"] == DiscountType.PERCENTAGE
        and values["discount_value"] > 100
    ):
        errors["discount_value"] = ["O desconto percentual não pode passar de 100%."]

    start = values.get("date_start") or timezone.now()
    if values["date_end"] <= start:
        errors["date_end"] = ["O término deve ser posterior ao início."]
    elif (
        values["status_promotion"] == PromotionStatus.ACTIVE
        and values["date_end"] <= timezone.now()
    ):
        errors["date_end"] = [
            "Para ativar a promoção, o término deve ser uma data futura."
        ]

    if errors:
        raise ApiValidationFailure(errors)


def _target_values(data: dict) -> dict:
    return {
        field: data[key]
        for key, field in (
            ("id_workshop_service", "workshop_service_id"),
            ("id_product", "product_id"),
        )
        if key in data
    }


@transactional
def create_promotion(workshop_id: int, data: dict) -> Promotion:
    values = {
        field: data[field] for field in PROMOTION_FIELDS if data.get(field) is not None
    }
    values.update(_target_values(data))
    _validate_promotion(workshop_id, values)
    promotion = Promotion.objects.create(workshop_id=workshop_id, **values)
    if data.get("image") is not None:
        apply_image_changes(
            promotion, {"image_url": data["image"]}, folder="promotions"
        )
    return promotion


@transactional
def update_promotion(promotion: Promotion, data: dict) -> Promotion:
    """PATCH parcial; a promoção (efetivamente) expirada não muda mais (409)."""
    promotion = Promotion.objects.select_for_update(no_key=True).get(pk=promotion.pk)
    effective = PromotionEffective.objects.get(pk=promotion.pk).effective_status
    if effective == PromotionStatus.EXPIRED:
        raise ApiConflict(EXPIRED_IS_FINAL)

    changes = {field: data[field] for field in PROMOTION_FIELDS if field in data}
    changes.update(_target_values(data))
    current = {
        field: getattr(promotion, field)
        for field in (*PROMOTION_FIELDS, "workshop_service_id", "product_id")
    }
    _validate_promotion(promotion.workshop_id, {**current, **changes})

    deactivating = (
        changes.get("status_promotion") == PromotionStatus.INACTIVE
        and promotion.status_promotion != PromotionStatus.INACTIVE
    )
    for field, value in changes.items():
        setattr(promotion, field, value)
    if changes:
        promotion.save(update_fields=list(changes))
    if (
        deactivating
    ):  # a trigger cancelou as divulgações; as pagas vão para estorno (BE-076)
        refund_cancelled_advertisements(promotion_id=promotion.pk)
    if "image" in data:
        apply_image_changes(
            promotion, {"image_url": data["image"]}, folder="promotions"
        )
    return promotion


def advertising_price(date_start, date_end) -> Decimal:
    """DP-09: diárias (arredondadas para cima, mínimo 1) × `SAM_ADVERTISING_PRICE_PER_DAY`."""
    days = max(1, math.ceil((date_end - date_start).total_seconds() / 86400))
    per_day = Decimal(str(settings.SAM_ADVERTISING_PRICE_PER_DAY))
    return (per_day * days).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


@transactional
def request_advertisement(promotion: Promotion, data: dict) -> PromotionAdvertisement:
    """BE-064: nasce `pending/pending` com preço calculado pelo servidor. Só vai ao ar
    com pagamento confirmado pelo admin (BE-076) e dentro do período."""
    promotion = Promotion.objects.select_for_update(no_key=True).get(pk=promotion.pk)
    start, end = data["date_start"], data["date_end"]

    if end <= start:
        raise ApiValidationFailure(
            {"date_end": ["O término deve ser posterior ao início."]}
        )
    if start < promotion.date_start or end > promotion.date_end:
        raise ApiValidationFailure({"detail": PERIOD_OUTSIDE})
    if end <= timezone.now():
        raise ApiValidationFailure(
            {"date_end": ["O período da divulgação já terminou."]}
        )
    if promotion.status_promotion != PromotionStatus.ACTIVE:
        raise ApiConflict("A divulgação exige uma promoção ativa.")

    name = save_image(data["image"], "advertisements")
    try:
        with transaction.atomic():
            return PromotionAdvertisement.objects.create(
                promotion=promotion,
                image_url=name,
                date_start=start,
                date_end=end,
                advertising_price=advertising_price(start, end),
            )
    except Exception:
        delete_stored_image(name)
        raise


# ------------------------------------------ pagamento e ativação (BE-076, DP-09)

OPEN_ADVERTISEMENT = (AdvertisementStatus.PENDING, AdvertisementStatus.ACTIVE)


def _lock_advertisement(advertisement_id: int) -> PromotionAdvertisement:
    return (
        PromotionAdvertisement.objects.select_for_update(of=("self",))
        .select_related("promotion")
        .get(pk=advertisement_id)
    )


@transactional
def activate_due_advertisements(
    *, advertisement_id: int | None = None, skip_locked: bool = False
) -> int:
    """Põe no ar as divulgações pagas e pendentes cujo período começou (e não
    terminou) com a promoção ativa. Usa o NOW() da transação — o mesmo da trigger,
    que revalida tudo. Idempotente; `skip_locked` é para a rotina periódica."""
    now = CurrentTimestamp()
    due = PromotionAdvertisement.objects.filter(
        status_advertisement=AdvertisementStatus.PENDING,
        payment_status=PaymentStatus.PAID,
        date_start__lte=now,
        date_end__gt=now,
        promotion__status_promotion=PromotionStatus.ACTIVE,
    )
    if advertisement_id is not None:
        due = due.filter(pk=advertisement_id)
    ids = list(
        due.select_for_update(of=("self",), skip_locked=skip_locked)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if not ids:
        return 0
    PromotionAdvertisement.objects.filter(pk__in=ids).update(
        status_advertisement=AdvertisementStatus.ACTIVE
    )
    if (
        advertisement_id is None
    ):  # pela rotina; na confirmação o aviso é `advertisement_paid`
        for advertisement in PromotionAdvertisement.objects.filter(
            pk__in=ids
        ).select_related("promotion"):
            events.advertisement_live(advertisement)
    return len(ids)


@transactional
def refund_cancelled_advertisements(
    *,
    promotion_id: int | None = None,
    advertisement_id: int | None = None,
    skip_locked: bool = False,
) -> int:
    """Divulgação `cancelled` com pagamento `paid` → `refunded` (marcada para estorno)."""
    pending_refund = PromotionAdvertisement.objects.filter(
        status_advertisement=AdvertisementStatus.CANCELLED,
        payment_status=PaymentStatus.PAID,
    )
    if promotion_id is not None:
        pending_refund = pending_refund.filter(promotion_id=promotion_id)
    if advertisement_id is not None:
        pending_refund = pending_refund.filter(pk=advertisement_id)
    advertisements = list(
        pending_refund.select_for_update(of=("self",), skip_locked=skip_locked)
        .select_related("promotion")
        .order_by("pk")
    )
    if not advertisements:
        return 0
    PromotionAdvertisement.objects.filter(
        pk__in=[ad.pk for ad in advertisements]
    ).update(payment_status=PaymentStatus.REFUNDED)
    for advertisement in advertisements:
        events.advertisement_refunded(advertisement)
    return len(advertisements)


@transactional
def confirm_advertisement_payment(advertisement_id: int) -> PromotionAdvertisement:
    """Admin confirma o pagamento (DP-09). Se o período já começou, entra no ar agora."""
    advertisement = _lock_advertisement(advertisement_id)
    if advertisement.status_advertisement != AdvertisementStatus.PENDING:
        raise ApiConflict(
            "Só é possível confirmar o pagamento de uma divulgação pendente."
        )
    if advertisement.payment_status == PaymentStatus.PAID:
        raise ApiConflict("O pagamento desta divulgação já foi confirmado.")
    if advertisement.date_end <= timezone.now():
        raise ApiConflict("O período desta divulgação já terminou.")
    advertisement.payment_status = PaymentStatus.PAID
    advertisement.save(update_fields=["payment_status"])
    live = activate_due_advertisements(advertisement_id=advertisement.pk) > 0
    advertisement.refresh_from_db()
    events.advertisement_paid(advertisement, live=live)
    return advertisement


@transactional
def mark_advertisement_payment_failed(advertisement_id: int) -> PromotionAdvertisement:
    """Pagamento recusado/não identificado: a divulgação continua pendente e pode ser paga depois."""
    advertisement = _lock_advertisement(advertisement_id)
    if (advertisement.status_advertisement, advertisement.payment_status) != (
        AdvertisementStatus.PENDING,
        PaymentStatus.PENDING,
    ):
        raise ApiConflict("Só um pagamento pendente pode ser marcado como falho.")
    advertisement.payment_status = PaymentStatus.FAILED
    advertisement.save(update_fields=["payment_status"])
    return advertisement


@transactional
def cancel_advertisement(advertisement_id: int) -> bool:
    """Tira do ar (ou cancela antes de ir ao ar); se estava paga, marca o estorno.
    `False` se já estava concluída ou cancelada (nada muda)."""
    advertisement = _lock_advertisement(advertisement_id)
    if advertisement.status_advertisement not in OPEN_ADVERTISEMENT:
        return False
    advertisement.status_advertisement = AdvertisementStatus.CANCELLED
    advertisement.save(update_fields=["status_advertisement"])
    refund_cancelled_advertisements(advertisement_id=advertisement.pk)
    return True
