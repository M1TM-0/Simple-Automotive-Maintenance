"""BE-076 (DP-09): confirmação manual do pagamento, ativação das divulgações pagas e estorno."""

import logging
import time
from datetime import timedelta
from io import StringIO

import pytest
from apps.core.tests.factories import (
    PromotionAdvertisementFactory,
    PromotionFactory,
    make_ready_workshop,
)
from apps.notifications.models import Notification
from apps.promotions.models import AdvertisementEffective, PromotionAdvertisement
from django.core.management import call_command
from django.db import connection
from django.test import Client as BrowserClient
from django.utils import timezone

ADMIN = "/admin/promotions/promotionadvertisement/"


@pytest.fixture
def staff_browser(django_user_model):
    browser = BrowserClient()
    browser.force_login(
        django_user_model.objects.create_superuser(
            "chefe", "chefe@exemplo.com", "SenhaAdmin123"
        )
    )
    return browser


def run_action(browser, action, *advertisements):
    return browser.post(
        ADMIN,
        {"action": action, "_selected_action": [str(ad.pk) for ad in advertisements]},
        follow=True,
    )


def state(advertisement):
    advertisement.refresh_from_db()
    return advertisement.status_advertisement, advertisement.payment_status


def workshop_titles(workshop):
    return list(
        Notification.objects.filter(workshop=workshop)
        .order_by("id_notification")
        .values_list("title", flat=True)
    )


def future_advertisement(workshop, **kwargs):
    """Divulgação que começa amanhã (dentro da promoção da fábrica, que vai até +10 dias)."""
    now = timezone.now()
    return PromotionAdvertisementFactory(
        promotion=PromotionFactory(workshop=workshop, title="Óleo 20% off"),
        date_start=now + timedelta(days=1),
        date_end=now + timedelta(days=3),
        **kwargs,
    )


def run_jobs():
    out = StringIO()
    call_command("run_expiration_jobs", stdout=out)
    return out.getvalue()


# ------------------------------------------------------ admin (sem relógio)


@pytest.mark.django_db
class TestAdminActions:
    def test_confirm_payment_before_the_period_waits_for_the_start(
        self, staff_browser, django_capture_on_commit_callbacks
    ):
        workshop = make_ready_workshop()
        advertisement = future_advertisement(workshop)

        with django_capture_on_commit_callbacks(execute=True):
            response = run_action(staff_browser, "confirm_payment", advertisement)

        assert response.status_code == 200
        assert state(advertisement) == ("pending", "paid")
        [message] = Notification.objects.filter(workshop=workshop).values_list(
            "message", flat=True
        )
        assert "R$ 50,00" in message and "Ela entra no ar em" in message
        assert workshop_titles(workshop) == ["Pagamento confirmado"]

    def test_confirm_is_refused_twice_and_for_closed_advertisements(
        self, staff_browser, caplog
    ):
        workshop = make_ready_workshop()
        paid = future_advertisement(workshop, payment_status="paid")
        cancelled = future_advertisement(workshop)
        PromotionAdvertisement.objects.filter(pk=cancelled.pk).update(
            status_advertisement="cancelled"
        )

        with caplog.at_level(logging.INFO, logger="sam.audit"):
            page = run_action(
                staff_browser, "confirm_payment", paid, cancelled
            ).content.decode()

        assert "já foi confirmado" in page and "divulgação pendente" in page
        assert state(paid) == ("pending", "paid") and state(cancelled) == (
            "cancelled",
            "pending",
        )
        assert not [
            r
            for r in caplog.records
            if r.name == "sam.audit" and "advertisement" in r.getMessage()
        ]

    def test_failed_payment_can_be_confirmed_later(self, staff_browser):
        advertisement = future_advertisement(make_ready_workshop())

        run_action(staff_browser, "mark_payment_failed", advertisement)
        assert state(advertisement) == ("pending", "failed")
        run_action(staff_browser, "confirm_payment", advertisement)
        assert state(advertisement) == ("pending", "paid")

    def test_cancel_paid_advertisement_marks_the_refund(
        self, staff_browser, django_capture_on_commit_callbacks, caplog
    ):
        workshop = make_ready_workshop()
        advertisement = future_advertisement(workshop, payment_status="paid")

        with (
            caplog.at_level(logging.INFO, logger="sam.audit"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            run_action(staff_browser, "cancel_advertisements", advertisement)

        assert state(advertisement) == ("cancelled", "refunded")
        assert workshop_titles(workshop) == ["Estorno da divulgação"]
        [record] = [r for r in caplog.records if r.name == "sam.audit"]
        assert (record.getMessage(), record.target_id, record.payment_status) == (
            "admin.advertisement.cancel",
            str(advertisement.pk),
            "refunded",
        )

    def test_cancel_unpaid_advertisement_has_no_refund(self, staff_browser):
        advertisement = future_advertisement(make_ready_workshop())
        run_action(staff_browser, "cancel_advertisements", advertisement)
        assert state(advertisement) == ("cancelled", "pending")

    def test_admin_is_read_only(self, staff_browser):
        advertisement = future_advertisement(make_ready_workshop())

        assert staff_browser.get(f"{ADMIN}add/").status_code == 403
        assert (
            staff_browser.get(f"{ADMIN}{advertisement.pk}/delete/").status_code == 403
        )
        page = staff_browser.get(f"{ADMIN}{advertisement.pk}/change/").content.decode()
        assert (
            'name="payment_status"' not in page
            and 'name="status_advertisement"' not in page
        )

    def test_changelist_filters_by_payment(self, staff_browser):
        workshop = make_ready_workshop()
        future_advertisement(workshop, payment_status="paid")
        future_advertisement(workshop)

        page = staff_browser.get(
            ADMIN, {"payment_status__exact": "paid"}
        ).content.decode()

        assert page.count('name="_selected_action"') == 1


@pytest.mark.django_db
class TestPromotionDeactivation:
    def test_deactivated_promotion_cancels_and_refunds_the_paid_advertisement(
        self, account_session, django_capture_on_commit_callbacks
    ):
        """Critério: promoção desativada → divulgação cancelada e pagamento marcado para estorno."""
        workshop = make_ready_workshop()
        paid = future_advertisement(workshop, payment_status="paid")
        unpaid = PromotionAdvertisementFactory(
            promotion=paid.promotion, date_start=paid.date_start, date_end=paid.date_end
        )
        api = account_session(workshop, "workshop")

        with django_capture_on_commit_callbacks(execute=True):
            response = api.patch(
                f"/api/workshop/promotions/{paid.promotion_id}/",
                {"status_promotion": "inactive"},
                format="multipart",
            )

        assert response.status_code == 200
        assert state(paid) == ("cancelled", "refunded")
        assert state(unpaid) == ("cancelled", "pending")
        assert workshop_titles(workshop) == ["Estorno da divulgação"]
        listed = api.get(
            f"/api/workshop/promotions/{paid.promotion_id}/advertisements/"
        ).json()["results"]
        assert {(a["id"], a["payment_status"]) for a in listed} == {
            (paid.pk, "refunded"),
            (unpaid.pk, "pending"),
        }

    def test_unpaid_advertisement_is_never_activated(self):
        workshop = make_ready_workshop()
        promotion = PromotionFactory(workshop=workshop)
        advertisement = PromotionAdvertisementFactory(
            promotion=promotion, date_start=timezone.now() - timedelta(hours=2)
        )

        for _ in range(2):
            assert "divulgações ativadas: 0" in run_jobs()

        assert state(advertisement) == ("pending", "pending")


# ------------------------------------------- rotina com relógio real (BE-076)


@pytest.mark.django_db(transaction=True)
class TestActivationWithRealClock:
    """Cada chamada é uma transação própria: o NOW() do banco é o relógio de verdade."""

    def test_job_activates_paid_advertisement_whose_start_arrived(self, api_client):
        workshop = make_ready_workshop()
        promotion = PromotionFactory(workshop=workshop, title="Óleo 20% off")
        advertisement = PromotionAdvertisementFactory(
            promotion=promotion,
            date_start=timezone.now() + timedelta(milliseconds=300),
            payment_status="paid",
        )
        assert "divulgações ativadas: 0" in run_jobs()  # ainda não começou
        time.sleep(0.5)

        output = run_jobs()

        assert "divulgações ativadas: 1" in output
        assert state(advertisement) == ("active", "paid")
        assert (
            AdvertisementEffective.objects.get(pk=advertisement.pk).is_running_now
            is True
        )
        kinds = {
            (item["kind"], item["id"])
            for item in api_client.get("/api/promotions/").json()["results"]
        }
        assert ("advertisement", advertisement.pk) in kinds
        assert workshop_titles(workshop) == ["Divulgação no ar"]
        assert "divulgações ativadas: 0" in run_jobs()  # idempotente

    def test_unpaid_advertisement_in_period_stays_off_the_air(self, api_client):
        workshop = make_ready_workshop()
        advertisement = PromotionAdvertisementFactory(
            promotion=PromotionFactory(workshop=workshop),
            date_start=timezone.now() - timedelta(minutes=5),
        )

        run_jobs()

        assert state(advertisement) == ("pending", "pending")
        assert (
            AdvertisementEffective.objects.get(pk=advertisement.pk).is_running_now
            is False
        )
        kinds = {
            item["kind"]
            for item in api_client.get("/api/promotions/").json()["results"]
        }
        assert "advertisement" not in kinds

    def test_confirming_payment_inside_the_period_activates_now(
        self, django_user_model
    ):
        browser = BrowserClient()
        browser.force_login(
            django_user_model.objects.create_superuser(
                "chefe", "c@exemplo.com", "SenhaAdmin123"
            )
        )
        workshop = make_ready_workshop()
        advertisement = PromotionAdvertisementFactory(
            promotion=PromotionFactory(workshop=workshop, title="Pneus"),
            date_start=timezone.now() - timedelta(minutes=5),
        )

        run_action(browser, "confirm_payment", advertisement)

        assert state(advertisement) == ("active", "paid")
        assert workshop_titles(workshop) == ["Divulgação no ar"]
        message = Notification.objects.get(workshop=workshop).message
        assert message.startswith(
            "Pagamento confirmado: a divulgação da promoção “Pneus” já está no ar"
        )

    def test_paid_advertisement_of_an_expired_promotion_is_refunded_by_the_job(self):
        workshop = make_ready_workshop()
        promotion = PromotionFactory(
            workshop=workshop, date_end=timezone.now() + timedelta(milliseconds=600)
        )
        advertisement = PromotionAdvertisementFactory(
            promotion=promotion,
            date_start=timezone.now() + timedelta(milliseconds=300),
            date_end=promotion.date_end,
            payment_status="paid",
        )
        time.sleep(0.8)  # o período inteiro passou sem a rotina rodar

        output = run_jobs()

        assert "promoções expiradas: 1" in output and "estornos marcados: 1" in output
        assert state(advertisement) == ("cancelled", "refunded")
        assert workshop_titles(workshop) == ["Estorno da divulgação"]

    def test_activation_waits_for_a_locked_promotion_without_deadlock(self):
        """A desativação da promoção (FOR NO KEY UPDATE) e a ativação pela rotina não se travam."""
        import threading

        from apps.promotions.services import (
            activate_due_advertisements,
            update_promotion,
        )
        from django.db import connections

        workshop = make_ready_workshop()
        promotion = PromotionFactory(workshop=workshop)
        advertisement = PromotionAdvertisementFactory(
            promotion=promotion,
            date_start=timezone.now() - timedelta(minutes=1),
            payment_status="paid",
        )
        barrier = threading.Barrier(2)
        errors = []

        def deactivate():
            try:
                barrier.wait()
                update_promotion(promotion, {"status_promotion": "inactive"})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        def activate():
            try:
                barrier.wait()
                activate_due_advertisements()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=deactivate),
            threading.Thread(target=activate),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors
        # Qualquer ordem termina no mesmo lugar: promoção inativa e divulgação fora do ar e estornada.
        assert state(advertisement) == ("cancelled", "refunded")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status_promotion FROM promotion WHERE id_promotion = %s",
                [promotion.pk],
            )
            assert cursor.fetchone()[0] == "inactive"
