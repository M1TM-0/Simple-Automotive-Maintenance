"""Casos de uso de avaliações e denúncias (BE-059…BE-061).

Notificações (BE-070): avaliação recebida → oficina; resposta → cliente.
"""

import uuid

from apps.attendances.models import Budget
from apps.core.db import ClockTimestamp
from apps.core.exceptions import ApiConflict
from apps.core.transactions import transactional
from apps.notifications import events
from apps.promotions.models import Promotion, PromotionAdvertisement
from apps.reviews.models import Denunciation, DenunciationStatus, Review, ReviewStatus
from rest_framework.exceptions import NotFound

ALREADY_REVIEWED = "Você já avaliou este atendimento."
ALREADY_DENOUNCED = "Você já denunciou este conteúdo e ele está em análise."


@transactional
def create_review(client_id: int, data: dict) -> Review:
    """BE-059: a posse do orçamento é validada aqui (o banco não conhece a sessão);
    orçamento aprovado + atendimento entregue são exigidos pela trigger (409)."""
    budget = Budget.objects.filter(
        pk=data["id_budget"], attendance__client_id=client_id
    ).first()
    if budget is None:
        raise NotFound("Orçamento não encontrado.")
    if Review.objects.filter(budget=budget).exists():
        raise ApiConflict(ALREADY_REVIEWED)  # `review_id_budget_key` cobre a corrida
    review = Review.objects.create(
        budget=budget, rating=data["rating"], comment=data.get("comment")
    )
    events.review_created(review)
    return review


@transactional
def respond_review(review: Review, text: str) -> Review:
    """BE-060: cria ou substitui a resposta pública; `date_response` acompanha (CHECK)."""
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status_review == ReviewStatus.HIDDEN:
        raise ApiConflict("Avaliações ocultas não podem ser respondidas.")
    review.workshop_response = text
    review.date_response = ClockTimestamp()
    review.save(update_fields=["workshop_response", "date_response"])
    review.refresh_from_db()
    events.review_responded(review)
    return review


def _resolve_target(target_type: str, target_id: str) -> dict:
    not_found = NotFound("Conteúdo não encontrado.")
    if target_type == "review":
        try:
            review_id = uuid.UUID(target_id)
        except ValueError:
            raise not_found from None
        review = (
            Review.objects.filter(pk=review_id)
            .exclude(status_review=ReviewStatus.HIDDEN)
            .first()
        )
        if review is None:
            raise not_found
        return {"review": review}
    if not target_id.isdigit():
        raise not_found
    model, field = (
        (Promotion, "promotion")
        if target_type == "promotion"
        else (PromotionAdvertisement, "advertisement")
    )
    target = model.objects.filter(pk=int(target_id)).first()
    if target is None:
        raise not_found
    return {field: target}


@transactional
def create_denunciation(client_id: int, data: dict) -> Denunciation:
    """BE-061: `{target_type,target_id}` → FK tipada. Uma denúncia em aberto por
    cliente e conteúdo (índices `uq_denunciation_open_*`). Denunciar não oculta o
    conteúdo (DP-15): a moderação decide em BE-073."""
    target = _resolve_target(data["target_type"], data["target_id"])
    open_statuses = (DenunciationStatus.PENDING, DenunciationStatus.IN_REVIEW)
    if Denunciation.objects.filter(
        client_id=client_id, status_denunciation__in=open_statuses, **target
    ).exists():
        raise ApiConflict(ALREADY_DENOUNCED)
    return Denunciation.objects.create(
        client_id=client_id,
        reason=data["reason"],
        description=data.get("description"),
        **target,
    )
