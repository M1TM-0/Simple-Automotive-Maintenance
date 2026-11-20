"""PROMOTION, PROMOTION_ADVERTISEMENT, DENUNCIATION e rotinas de expiração
(init.sql 9.8–9.11; RB-16…RB-18).

Vigência depende do `NOW()` do banco, fixo dentro de uma transação: os casos que
precisam ver o tempo passar usam `transaction=True` e esperam o fim do período.
"""

import itertools
import time
from datetime import timedelta

import pytest
from apps.core.tests.factories import (
    AttendanceFactory,
    BudgetFactory,
    BudgetItemFactory,
    DenunciationFactory,
    PromotionAdvertisementFactory,
    PromotionFactory,
)
from apps.promotions.models import Promotion, PromotionAdvertisement
from apps.reviews.models import Denunciation
from django.db import connection
from django.utils import timezone

from .support import CHECK, RAISE, covers, scalar, set_status, violates

pytestmark = pytest.mark.db_rules

DAY = timedelta(days=1)


def _now():
    return timezone.now()


def _promotion(**kwargs):
    return PromotionFactory(**kwargs)


def _paid_running_ad(promotion, date_end=None):
    return PromotionAdvertisementFactory(
        promotion=promotion,
        payment_status="paid",
        status_advertisement="active",
        date_start=_now() - timedelta(hours=1),
        date_end=date_end or _now() + DAY,
    )


def _set(model, obj, **fields):
    model.objects.filter(pk=obj.pk).update(**fields)
    obj.refresh_from_db()


@pytest.mark.django_db
class TestPromotionValidate:
    """`trg_promotion_validate`."""

    @covers("trg_promotion_validate", positive=True)
    def test_active_current_or_scheduled_and_inactive_past(self):
        current = _promotion()
        scheduled = _promotion(date_start=_now() + DAY, date_end=_now() + 5 * DAY)
        past_inactive = _promotion(
            status_promotion="inactive",
            date_start=_now() - 10 * DAY,
            date_end=_now() - DAY,
        )
        assert (
            current.status_promotion,
            scheduled.status_promotion,
            past_inactive.status_promotion,
        ) == (
            "active",
            "active",
            "inactive",
        )
        _set(
            Promotion, past_inactive, title="Só o título"
        )  # não mexe em status/datas: sem validação

    @covers("trg_promotion_validate", negative=True)
    def test_cannot_be_born_expired(self):
        with violates(CHECK, "Uma promoção não pode ser criada já expirada."):
            _promotion(status_promotion="expired")

    @covers("trg_promotion_validate", negative=True)
    def test_cannot_be_active_after_its_end(self):
        with violates(
            CHECK, "Uma promoção não pode ser ativada fora do período de validade"
        ):
            _promotion(date_start=_now() - 10 * DAY, date_end=_now() - DAY)

    @covers("trg_promotion_validate", negative=True)
    def test_reactivating_an_ended_promotion_is_refused(self):
        promotion = _promotion(
            status_promotion="inactive",
            date_start=_now() - 10 * DAY,
            date_end=_now() - DAY,
        )
        with violates(
            CHECK, "Uma promoção não pode ser ativada fora do período de validade"
        ):
            _set(Promotion, promotion, status_promotion="active")

    @covers("trg_promotion_validate", positive=True)
    def test_inactive_and_active_toggle_within_the_period(self):
        promotion = _promotion()
        _set(Promotion, promotion, status_promotion="inactive")
        _set(Promotion, promotion, status_promotion="active")
        assert promotion.status_promotion == "active"

    @covers("trg_promotion_validate", negative=True)
    def test_only_active_promotions_expire(self):
        promotion = _promotion(
            status_promotion="inactive",
            date_start=_now() - 10 * DAY,
            date_end=_now() - DAY,
        )
        with violates(
            CHECK, "Somente uma promoção ativa pode expirar (status atual: inactive)."
        ):
            _set(Promotion, promotion, status_promotion="expired")

    @covers("trg_promotion_validate", negative=True)
    def test_cannot_expire_within_the_period(self):
        promotion = _promotion()
        with violates(CHECK, "A promoção ainda está no período"):
            _set(Promotion, promotion, status_promotion="expired")

    def test_end_after_start_and_percentage_up_to_100(self):
        with violates(CHECK):
            _promotion(date_start=_now() + DAY, date_end=_now())
        with violates(CHECK):
            _promotion(discount_value="100.01")


@pytest.mark.django_db
class TestPromotionCloseAdvertisements:
    """`trg_promotion_close_advertisements` (desativação; a expiração está na classe com relógio real)."""

    @covers("trg_promotion_close_advertisements", positive=True)
    def test_deactivation_cancels_pending_and_running_ads(self):
        promotion = _promotion()
        pending = PromotionAdvertisementFactory(promotion=promotion)
        running = _paid_running_ad(promotion)
        _set(Promotion, promotion, status_promotion="inactive")
        pending.refresh_from_db()
        running.refresh_from_db()
        assert (pending.status_advertisement, running.status_advertisement) == (
            "cancelled",
            "cancelled",
        )
        assert running.payment_status == "paid", (
            "estorno é regra do backend, não do trigger"
        )

    @covers("trg_promotion_close_advertisements", negative=True)
    def test_other_updates_leave_ads_alone(self):
        promotion = _promotion()
        ad = PromotionAdvertisementFactory(promotion=promotion)
        _set(Promotion, promotion, title="Novo título", description="x")
        ad.refresh_from_db()
        assert ad.status_advertisement == "pending"


@pytest.mark.django_db
class TestAdvertisementValidate:
    """`trg_promotion_advertisement_validate`."""

    @covers("trg_promotion_advertisement_validate", positive=True)
    def test_pending_ad_inside_the_promotion_and_activation_after_payment(self):
        promotion = _promotion()
        ad = PromotionAdvertisementFactory(
            promotion=promotion, date_start=_now() - timedelta(minutes=5)
        )
        _set(
            PromotionAdvertisement, ad, payment_status="paid"
        )  # sem campo validado: passa direto
        _set(PromotionAdvertisement, ad, status_advertisement="active")
        assert ad.status_advertisement == "active"

    @covers("trg_promotion_advertisement_validate", negative=True)
    def test_requires_an_active_promotion(self):
        promotion = _promotion(status_promotion="inactive")
        with violates(RAISE, "A divulgação exige uma promoção ativa."):
            PromotionAdvertisementFactory(promotion=promotion)

    @covers("trg_promotion_advertisement_validate", negative=True)
    def test_period_inside_the_promotion(self):
        promotion = _promotion(date_end=_now() + 3 * DAY)
        with violates(
            RAISE, "O período da divulgação deve estar contido no período da promoção."
        ):
            PromotionAdvertisementFactory(
                promotion=promotion, date_end=_now() + 4 * DAY
            )

    @covers("trg_promotion_advertisement_validate", negative=True)
    def test_period_cannot_be_over(self):
        promotion = _promotion(date_start=_now() - 10 * DAY)
        with violates(RAISE, "O período da divulgação já terminou."):
            PromotionAdvertisementFactory(
                promotion=promotion, date_start=_now() - 5 * DAY, date_end=_now() - DAY
            )

    @covers("trg_promotion_advertisement_validate", negative=True)
    def test_activation_requires_payment(self):
        ad = PromotionAdvertisementFactory(date_start=_now() - timedelta(minutes=5))
        with violates(
            RAISE, "A divulgação só pode ser ativada após a confirmação do pagamento."
        ):
            _set(PromotionAdvertisement, ad, status_advertisement="active")

    @covers("trg_promotion_advertisement_validate", negative=True)
    def test_activation_only_inside_the_contracted_period(self):
        ad = PromotionAdvertisementFactory(
            date_start=_now() + DAY, date_end=_now() + 2 * DAY, payment_status="paid"
        )
        with violates(
            RAISE, "A divulgação só pode ser ativada dentro do período contratado."
        ):
            _set(PromotionAdvertisement, ad, status_advertisement="active")


@pytest.mark.django_db
class TestDenunciation:
    """`denunciation_transition_allowed` e `trg_denunciation_guard`."""

    STATUSES = ("pending", "in_review", "upheld", "dismissed")
    ALLOWED = {
        ("pending", "in_review"),
        ("pending", "upheld"),
        ("pending", "dismissed"),
        ("in_review", "upheld"),
        ("in_review", "dismissed"),
    }

    @covers("denunciation_transition_allowed", positive=True, negative=True)
    @pytest.mark.parametrize(
        ("old", "new"), list(itertools.product(STATUSES, STATUSES))
    )
    def test_every_pair(self, old, new):
        assert scalar("SELECT denunciation_transition_allowed(%s, %s)", [old, new]) is (
            (old, new) in self.ALLOWED
        )

    @covers("trg_denunciation_guard", positive=True)
    def test_lifecycle_and_resolution_date(self):
        denunciation = DenunciationFactory()
        _set(
            Denunciation,
            denunciation,
            reason="other",
            description="Ajuste enquanto pendente",
        )
        _set(Denunciation, denunciation, status_denunciation="in_review")
        _set(
            Denunciation,
            denunciation,
            status_denunciation="upheld",
            moderation_decision="Procede",
        )
        assert denunciation.date_resolution is not None

    @covers("trg_denunciation_guard", negative=True)
    @pytest.mark.parametrize(
        "fields", [{"status_denunciation": "upheld"}, {"moderation_decision": "x"}]
    )
    def test_must_be_born_pending_without_decision(self, fields):
        with violates(
            CHECK,
            "Uma denúncia deve ser criada como pending, sem decisão nem data de resolução.",
        ):
            DenunciationFactory(**fields)

    @covers("trg_denunciation_guard", negative=True)
    def test_author_and_content_are_immutable(self):
        denunciation = DenunciationFactory()
        with violates(
            CHECK,
            "Cliente, conteúdo denunciado e data de criação de uma denúncia não podem ser alterados.",
        ):
            _set(Denunciation, denunciation, promotion=PromotionFactory())

    @covers("trg_denunciation_guard", negative=True)
    def test_reason_frozen_after_pending(self):
        denunciation = DenunciationFactory()
        _set(Denunciation, denunciation, status_denunciation="in_review")
        with violates(
            CHECK,
            "O motivo e a descrição só podem ser alterados enquanto a denúncia está pending.",
        ):
            _set(Denunciation, denunciation, reason="other")

    @covers("trg_denunciation_guard", negative=True)
    @pytest.mark.parametrize(
        ("path", "new"),
        [
            (["in_review"], "pending"),
            (["dismissed"], "upheld"),
            (["upheld"], "in_review"),
        ],
    )
    def test_forbidden_transitions(self, path, new):
        denunciation = DenunciationFactory()
        for status in path:
            decision = (
                {"moderation_decision": "Decisão"}
                if status in ("upheld", "dismissed")
                else {}
            )
            _set(Denunciation, denunciation, status_denunciation=status, **decision)
        with violates(CHECK, f"Transição de denúncia inválida: {path[-1]} -> {new}."):
            _set(Denunciation, denunciation, status_denunciation=new)

    @covers("trg_denunciation_guard", negative=True)
    def test_resolved_decision_is_immutable(self):
        denunciation = DenunciationFactory()
        _set(
            Denunciation,
            denunciation,
            status_denunciation="dismissed",
            moderation_decision="Não procede",
        )
        with violates(
            CHECK, "A decisão de uma denúncia já resolvida não pode ser alterada."
        ):
            _set(Denunciation, denunciation, moderation_decision="Reescrita")


def _db_now():
    with connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        return cursor.fetchone()[0]


def _wait_until(moment):
    remaining = (moment - _db_now()).total_seconds()
    if remaining > 0:
        time.sleep(remaining + 0.05)


@pytest.mark.django_db(transaction=True)
class TestExpirationWithRealClock:
    """Expiração de promoções, conclusão de divulgações e `run_expiration_jobs()`."""

    def _ending_soon(self, seconds=0.6):
        end = _db_now() + timedelta(seconds=seconds)
        promotion = PromotionFactory(date_start=end - 2 * DAY, date_end=end)
        return promotion, end

    @covers(
        "expire_promotions",
        "trg_promotion_close_advertisements",
        "trg_promotion_validate",
        positive=True,
    )
    @covers(
        "complete_finished_advertisements",
        "expire_promotions",
        "run_expiration_jobs",
        negative=True,
    )
    def test_expired_promotion_completes_running_ads_and_is_final(self):
        promotion, end = self._ending_soon()
        running = _paid_running_ad(promotion, date_end=end)
        pending = PromotionAdvertisementFactory(promotion=promotion, date_end=end)
        vigente = PromotionFactory()
        inactive = PromotionFactory(status_promotion="inactive")

        assert scalar("SELECT expire_promotions()") == 0, "ainda no período"
        _wait_until(end)
        assert scalar("SELECT expire_promotions()") == 1
        assert scalar("SELECT expire_promotions()") == 0, "idempotente"

        for obj in (promotion, running, pending, vigente, inactive):
            obj.refresh_from_db()
        assert promotion.status_promotion == "expired"
        assert (running.status_advertisement, pending.status_advertisement) == (
            "completed",
            "cancelled",
        )
        assert (vigente.status_promotion, inactive.status_promotion) == (
            "active",
            "inactive",
        )

        with violates(CHECK, "Uma promoção expirada é definitiva"):
            _set(Promotion, promotion, status_promotion="active", date_end=_now() + DAY)
        assert scalar("SELECT complete_finished_advertisements()") == 0
        assert scalar("SELECT ROW(r.*)::text FROM run_expiration_jobs() r") == "(0,0,0)"

    @covers("complete_finished_advertisements", "run_expiration_jobs", positive=True)
    def test_finished_ads_complete_and_jobs_report_counts(self):
        promotion = PromotionFactory(date_end=_now() + 10 * DAY)
        end = _db_now() + timedelta(seconds=0.6)
        ad = _paid_running_ad(promotion, date_end=end)
        still_running = _paid_running_ad(promotion)

        attendance = AttendanceFactory()
        budget = BudgetFactory(
            attendance=attendance,
            date_creation=_now() - 10 * DAY,
            date_validity=_now() - DAY,
        )
        BudgetItemFactory(budget=budget)
        set_status(attendance, "waiting_approval")

        _wait_until(end)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT budgets_expired, promotions_expired, advertisements_completed FROM run_expiration_jobs()"
            )
            assert cursor.fetchone() == (1, 0, 1)
            cursor.execute(
                "SELECT budgets_expired, promotions_expired, advertisements_completed FROM run_expiration_jobs()"
            )
            assert cursor.fetchone() == (0, 0, 0)

        ad.refresh_from_db()
        still_running.refresh_from_db()
        attendance.refresh_from_db()
        assert (ad.status_advertisement, still_running.status_advertisement) == (
            "completed",
            "active",
        )
        assert attendance.status_attendance == "requested"
