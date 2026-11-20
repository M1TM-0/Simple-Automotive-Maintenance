"""Casos de uso da moderação: denúncias (BE-073) e serviços personalizados (BE-074).

**Denúncia (DP-15).** `pending → in_review → upheld | dismissed` (`pending` também
resolve direto); `upheld`/`dismissed` são finais (trigger `fn_denunciation_guard`).
Regras da aplicação, além das do banco: denúncia resolvida → 409; repetir o mesmo
status → 409 (a trigger ignora UPDATE sem mudança); resolver exige
`moderation_decision` (400 no serializer, CHECK no banco). Efeito de `upheld`
(o banco deixa a decisão para o backend):

- avaliação → `hidden` (some do perfil público, da nota média e do mapa);
- promoção → `inactive` (a trigger cancela as divulgações; as pagas vão para
  estorno — BE-076); promoção já expirada ou inativa fica como está;
- divulgação → `cancelled` (com estorno se paga); concluída fica como está.

Quem moderou fica no log de auditoria `sam.audit` (`AdminViewMixin`), sem coluna
nova (ADR 0015). O denunciante é notificado da resolução; a oficina, quando a
promoção/divulgação dela sai do ar.

**Serviço personalizado (RB-04).** Aprovar/rejeitar chamam as funções do banco
`approve_/reject_workshop_service_request`, que travam a linha, reaproveitam o
serviço global de mesmo nome normalizado (sem duplicar, inclusive sob
concorrência) e recusam solicitação não pendente. A oficina é notificada.
"""

from apps.catalog.models import SolicitationStatus, WorkshopService
from apps.core.exceptions import ApiConflict, ApiValidationFailure
from apps.core.transactions import transactional
from apps.notifications import events
from apps.promotions.models import Promotion, PromotionStatus
from apps.promotions.services import (
    cancel_advertisement,
    refund_cancelled_advertisements,
)
from apps.reviews.models import Denunciation, DenunciationStatus, Review, ReviewStatus
from django.db import connection
from rest_framework.exceptions import NotFound

RESOLVED = (DenunciationStatus.UPHELD, DenunciationStatus.DISMISSED)
ALREADY_RESOLVED = "Esta denúncia já foi resolvida."
ALREADY_IN_REVIEW = "Esta denúncia já está em análise."

DENUNCIATION_RELATED = (
    "client",
    "review__budget__workshop",
    "promotion__workshop",
    "advertisement__promotion__workshop",
)


# ----------------------------------------------------------------- denúncias


@transactional
def moderate_denunciation(
    denunciation_id: int, *, status: str, decision: str | None
) -> Denunciation:
    """`PATCH /admin/denunciations/{id}/`: analisa ou resolve uma denúncia."""
    denunciation = (
        Denunciation.objects.select_for_update().filter(pk=denunciation_id).first()
    )
    if denunciation is None:
        raise NotFound("Denúncia não encontrada.")
    if denunciation.status_denunciation in RESOLVED:
        raise ApiConflict(ALREADY_RESOLVED)
    if denunciation.status_denunciation == status:
        raise ApiConflict(ALREADY_IN_REVIEW)

    fields = ["status_denunciation"]
    denunciation.status_denunciation = status
    if decision is not None:
        denunciation.moderation_decision = decision
        fields.append("moderation_decision")
    denunciation.save(update_fields=fields)  # a trigger preenche date_resolution

    if status in RESOLVED:
        if status == DenunciationStatus.UPHELD:
            _take_down(denunciation)
        denunciation = Denunciation.objects.select_related(*DENUNCIATION_RELATED).get(
            pk=denunciation.pk
        )
        events.denunciation_resolved(denunciation)
    return denunciation


def _take_down(denunciation: Denunciation) -> None:
    """Efeito de uma denúncia procedente sobre o conteúdo (DP-15)."""
    if denunciation.review_id:
        Review.objects.filter(pk=denunciation.review_id).exclude(
            status_review=ReviewStatus.HIDDEN
        ).update(status_review=ReviewStatus.HIDDEN)
        return

    if denunciation.promotion_id:
        promotion = Promotion.objects.select_for_update(no_key=True).get(
            pk=denunciation.promotion_id
        )
        if promotion.status_promotion != PromotionStatus.ACTIVE:
            return  # expirada é definitiva; inativa já está fora do ar
        promotion.status_promotion = PromotionStatus.INACTIVE
        promotion.save(
            update_fields=["status_promotion"]
        )  # a trigger cancela as divulgações
        refund_cancelled_advertisements(promotion_id=promotion.pk)
        events.content_removed_by_moderation(
            promotion.workshop_id, promotion_title=promotion.title, advertisement=False
        )
        return

    if cancel_advertisement(denunciation.advertisement_id):
        promotion = Promotion.objects.only("workshop_id", "title").get(
            advertisements__pk=denunciation.advertisement_id
        )
        events.content_removed_by_moderation(
            promotion.workshop_id, promotion_title=promotion.title, advertisement=True
        )


@transactional
def hide_review(review_id) -> Review:
    """`POST /admin/reviews/{id}/hide/`: oculta (idempotente). Some das listas públicas e da nota."""
    review = Review.objects.select_for_update().filter(pk=review_id).first()
    if review is None:
        raise NotFound("Avaliação não encontrada.")
    if review.status_review != ReviewStatus.HIDDEN:
        review.status_review = ReviewStatus.HIDDEN
        review.save(update_fields=["status_review"])
    return review


# ------------------------------------------------------ serviços personalizados


def _lock_request(request_id: int) -> WorkshopService:
    """Só serviços personalizados são solicitações; serviço do catálogo → 404."""
    workshop_service = (
        WorkshopService.objects.select_for_update()
        .filter(pk=request_id, status_solicitation__isnull=False)
        .first()
    )
    if workshop_service is None:
        raise NotFound("Solicitação não encontrada.")
    if workshop_service.status_solicitation != SolicitationStatus.PENDING:
        done = (
            "aprovada"
            if workshop_service.status_solicitation == SolicitationStatus.APPROVED
            else "rejeitada"
        )
        raise ApiConflict(f"Esta solicitação já foi {done}.")
    return workshop_service


def _global_service_exists(name: str) -> bool:
    """Mesma comparação de approve_workshop_service_request (índice uq_service_name_normalized)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM service "
            "WHERE normalize_service_name(name) = normalize_service_name(%s))",
            [name],
        )
        return cursor.fetchone()[0]


@transactional
def approve_service_request(
    request_id: int,
    *,
    category_id: int | None = None,
    name: str | None = None,
    description: str | None = None,
) -> WorkshopService:
    """Aprova: reaproveita o serviço global de mesmo nome normalizado ou cria um novo
    (aí a categoria é obrigatória: a informada ou a sugerida pela oficina)."""
    workshop_service = _lock_request(request_id)
    if (
        category_id is None
        and workshop_service.suggested_category_id is None
        and not _global_service_exists(name or workshop_service.name_local)
    ):
        raise ApiValidationFailure(
            {"id_category": ["Informe a categoria do novo serviço global."]}
        )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT approve_workshop_service_request(%s, %s, %s, %s)",
            [workshop_service.pk, category_id, name, description],
        )
    workshop_service.refresh_from_db()
    events.service_request_decided(workshop_service, approved=True)
    return workshop_service


@transactional
def reject_service_request(request_id: int, *, motivation: str) -> WorkshopService:
    """Rejeita: o serviço continua só no catálogo da oficina, com o motivo."""
    workshop_service = _lock_request(request_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT reject_workshop_service_request(%s, %s)",
            [workshop_service.pk, motivation],
        )
    workshop_service.refresh_from_db()
    events.service_request_decided(workshop_service, approved=False)
    return workshop_service
