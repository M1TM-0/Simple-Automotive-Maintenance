"""BE-069 (API de notificações) e BE-070 (geração pelos eventos de negócio)."""

import logging
from datetime import timedelta
from io import StringIO

import pytest
from apps.attendances.models import Budget
from apps.attendances.tests.conftest import Flow
from apps.chat.models import Chat
from apps.core.tests.factories import (
    ChatFactory,
    ClientFactory,
    NotificationFactory,
    VehicleFactory,
    WorkshopFactory,
)
from apps.core.throttles import PollingRateThrottle
from apps.notifications import events
from apps.notifications.models import Notification
from apps.notifications.services import notify, safe_url
from apps.notifications.views import UnreadCountView
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

URL = "/api/notifications/"
COUNT_URL = "/api/notifications/unread-count/"
READ_ALL_URL = "/api/notifications/read-all/"


def read_url(pk):
    return f"{URL}{pk}/read/"


def for_client(client):
    return Notification.objects.filter(client=client).order_by("id_notification")


def for_workshop(workshop):
    return Notification.objects.filter(workshop=workshop).order_by("id_notification")


@pytest.fixture
def flow(client_account, ready_workshop):
    return Flow(client_account, ready_workshop)


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """Executa os `on_commit` do bloco (os testes rodam dentro de uma transação)."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


# ================================================================== BE-069


@pytest.mark.django_db
class TestNotificationApi:
    def test_lists_only_own_notifications_newest_first(
        self, client_session, client_account
    ):
        older = NotificationFactory(
            client=client_account, title="Antiga", url="attendance.html?id=1"
        )
        newer = NotificationFactory(client=client_account, title="Nova")
        Notification.objects.filter(pk=older.pk).update(
            date_creation=timezone.now() - timedelta(hours=1)
        )
        NotificationFactory()  # de outro cliente
        NotificationFactory(client=None, workshop=WorkshopFactory())

        body = client_session.get(URL).json()

        assert body["count"] == 2
        assert [n["id"] for n in body["results"]] == [newer.pk, older.pk]
        item = body["results"][1]
        assert set(item) == {
            "id",
            "title",
            "message",
            "date_creation",
            "read_status",
            "url",
        }
        assert (item["title"], item["read_status"], item["url"]) == (
            "Antiga",
            False,
            "attendance.html?id=1",
        )
        assert body["results"][0]["url"] is None

    def test_unread_filter(self, client_session, client_account):
        unread = NotificationFactory(client=client_account)
        NotificationFactory(client=client_account, read_status=True)

        ids = [
            n["id"]
            for n in client_session.get(URL, {"unread": "true"}).json()["results"]
        ]

        assert ids == [unread.pk]
        assert client_session.get(URL, {"unread": ""}).json()["count"] == 2
        assert client_session.get(URL, {"unread": "talvez"}).status_code == 400

    def test_workshop_sees_its_own_even_during_setup(
        self, workshop_session, workshop_account
    ):
        mine = NotificationFactory(client=None, workshop=workshop_account)
        NotificationFactory(client=None, workshop=WorkshopFactory())

        body = workshop_session.get(URL).json()

        assert [n["id"] for n in body["results"]] == [mine.pk]

    def test_unread_count(self, client_session, client_account):
        for _ in range(3):
            NotificationFactory(client=client_account)
        NotificationFactory(client=client_account, read_status=True)
        NotificationFactory()

        response = client_session.get(COUNT_URL)

        assert response.status_code == 200
        assert response.json() == {"count": 3}

    def test_unread_count_is_one_cheap_query(
        self, client_session, client_account, django_assert_num_queries
    ):
        NotificationFactory(client=client_account)
        client_session.get(COUNT_URL)  # aquece a sessão

        # sessão + conta (autenticação) + 1 COUNT
        with django_assert_num_queries(3):
            client_session.get(COUNT_URL)

    def test_unread_count_uses_polling_throttle(self):
        assert UnreadCountView.throttle_classes == [PollingRateThrottle]

    def test_mark_one_as_read(self, client_session, client_account):
        notification = NotificationFactory(client=client_account)

        response = client_session.post(read_url(notification.pk))

        assert response.status_code == 204
        notification.refresh_from_db()
        assert notification.read_status is True
        assert (
            client_session.post(read_url(notification.pk)).status_code == 204
        )  # idempotente

    def test_mark_other_users_notification_is_404(
        self, client_session, workshop_session, workshop_account
    ):
        other_client = NotificationFactory()
        workshop_owned = NotificationFactory(client=None, workshop=workshop_account)

        assert client_session.post(read_url(other_client.pk)).status_code == 404
        assert client_session.post(read_url(workshop_owned.pk)).status_code == 404
        assert client_session.post(read_url(999_999)).status_code == 404
        other_client.refresh_from_db()
        assert other_client.read_status is False
        assert workshop_session.post(read_url(workshop_owned.pk)).status_code == 204

    def test_read_all_zeroes_the_counter_only_for_the_user(
        self, client_session, client_account
    ):
        for _ in range(3):
            NotificationFactory(client=client_account)
        other = NotificationFactory()

        assert client_session.post(READ_ALL_URL).status_code == 204

        assert client_session.get(COUNT_URL).json() == {"count": 0}
        other.refresh_from_db()
        assert other.read_status is False

    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("get", URL),
            ("get", COUNT_URL),
            ("post", read_url(1)),
            ("post", READ_ALL_URL),
        ],
    )
    def test_visitor_gets_401(self, api_client, method, url):
        response = getattr(api_client, method)(url)

        assert response.status_code == 401

    def test_admin_without_domain_profile_gets_403(self, admin_session):
        assert admin_session.get(URL).status_code == 403

    def test_safe_url_rule(self):
        assert safe_url("attendance.html?id=12") == "attendance.html?id=12"
        assert safe_url("w-reviews.html") == "w-reviews.html"
        for unsafe in (
            "http://evil.com",
            "//evil.com/x.html",
            "javascript:alert(1)",
            "a.html?x=<b>",
            "",
        ):
            assert safe_url(unsafe) is None


# ================================================================== BE-070


@pytest.mark.django_db
class TestAttendanceEvents:
    def test_new_attendance_notifies_the_workshop(
        self, client_session, client_account, ready_workshop, commit
    ):
        vehicle = VehicleFactory(
            client=client_account, brand="Fiat", model="Uno", plate="ABC1D23"
        )
        client_account.name = "Ana Souza"
        client_account.save(update_fields=["name"])

        with commit():
            response = client_session.post(
                "/api/attendances/",
                {"id_workshop": ready_workshop.pk, "id_vehicle": vehicle.pk},
                format="json",
            )

        assert response.status_code == 201
        [notification] = for_workshop(ready_workshop)
        assert notification.title == "Nova solicitação de atendimento"
        assert (
            notification.message
            == "Ana S. solicitou atendimento para Fiat Uno (ABC1D23)."
        )
        assert notification.url == f"w-attendance.html?id={response.json()['id']}"
        assert not for_client(client_account).exists()

    def test_budget_sent_notifies_the_client_once_with_url(
        self, ready_workshop_session, client_account, flow, commit
    ):
        attendance, budget = flow.budgeted()

        with commit():
            response = ready_workshop_session.post(
                f"/api/workshop/budgets/{budget.pk}/send/"
            )

        assert response.status_code == 200
        [notification] = for_client(client_account)
        assert notification.title == "Orçamento recebido"
        assert "R$ 160,00" in notification.message
        assert notification.url == f"attendance.html?id={attendance.pk}"

    @pytest.mark.parametrize(
        ("action", "title"),
        [("approve", "Orçamento aprovado"), ("reject", "Orçamento recusado")],
    )
    def test_budget_answer_notifies_the_workshop(
        self, client_session, ready_workshop, flow, commit, action, title
    ):
        attendance, budget = flow.waiting()

        with commit():
            response = client_session.post(f"/api/budgets/{budget.pk}/{action}/")

        assert response.status_code == 200
        [notification] = for_workshop(ready_workshop)
        assert notification.title == title
        assert notification.url == f"w-attendance.html?id={attendance.pk}"

    def test_client_cancel_notifies_the_workshop(
        self, client_session, ready_workshop, flow, commit
    ):
        attendance, _ = flow.at("requested")

        with commit():
            assert (
                client_session.post(
                    f"/api/attendances/{attendance.pk}/cancel/"
                ).status_code
                == 200
            )

        [notification] = for_workshop(ready_workshop)
        assert notification.title == "Atendimento cancelado pelo cliente"

    @pytest.mark.parametrize(
        ("start", "target", "title"),
        [
            ("approved", "in_progress", "Serviço iniciado"),
            ("in_progress", "completed", "Serviço concluído"),
            ("completed", "delivered", "Veículo entregue"),
            ("completed", "in_progress", "Serviço reaberto"),
            ("requested", "canceled", "Atendimento cancelado pela oficina"),
        ],
    )
    def test_workshop_transition_notifies_the_client(
        self, ready_workshop_session, client_account, flow, commit, start, target, title
    ):
        attendance, budget = flow.at(start)
        if target == "completed":  # concluir exige a execução de cada item marcada
            for item in (budget.service_item, budget.part_item):
                item.execution_status = "executed"
                item.save(update_fields=["execution_status"])

        with commit():
            response = ready_workshop_session.post(
                f"/api/workshop/attendances/{attendance.pk}/transition/",
                {"status": target},
                format="json",
            )

        assert response.status_code == 200, response.json()
        [notification] = for_client(client_account)
        assert notification.title == title
        assert notification.url == f"attendance.html?id={attendance.pk}"

    def test_failed_operation_creates_no_notification(
        self, ready_workshop_session, flow, commit
    ):
        attendance, _ = flow.at("requested")

        with commit():
            response = ready_workshop_session.post(
                f"/api/workshop/attendances/{attendance.pk}/transition/",
                {"status": "completed"},
                format="json",
            )

        assert response.status_code == 409
        assert not Notification.objects.exists()

    def test_notification_waits_for_the_commit(
        self, ready_workshop_session, flow, django_capture_on_commit_callbacks
    ):
        attendance, budget = flow.budgeted()

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            ready_workshop_session.post(f"/api/workshop/budgets/{budget.pk}/send/")

        assert len(callbacks) == 1
        assert not Notification.objects.exists()  # nada antes do commit
        callbacks[0]()
        assert Notification.objects.count() == 1

    def test_notification_failure_does_not_break_the_request(
        self, ready_workshop_session, flow, commit, monkeypatch, caplog
    ):
        attendance, budget = flow.budgeted()

        def broken(*args, **kwargs):
            raise RuntimeError("falha simulada")

        monkeypatch.setattr("apps.notifications.services._create", broken)
        with caplog.at_level(logging.ERROR, logger="sam.notifications"), commit():
            response = ready_workshop_session.post(
                f"/api/workshop/budgets/{budget.pk}/send/"
            )

        assert response.status_code == 200
        assert any(r.message == "notification_failed" for r in caplog.records)


@pytest.mark.django_db(transaction=True)
def test_rolled_back_operation_creates_no_notification(client_account, ready_workshop):
    """Sem a transação de teste em volta: o rollback é real e o callback é descartado."""
    flow = Flow(client_account, ready_workshop)
    attendance, budget = flow.budgeted()

    with pytest.raises(RuntimeError), transaction.atomic():
        events.budget_sent(budget)
        raise RuntimeError("desfaz")

    assert not Notification.objects.exists()

    with transaction.atomic():
        events.budget_sent(budget)
    assert Notification.objects.count() == 1


@pytest.mark.django_db
class TestReviewEvents:
    def test_review_and_response(
        self,
        client_session,
        ready_workshop_session,
        client_account,
        ready_workshop,
        flow,
        commit,
    ):
        attendance, budget = flow.delivered()

        with commit():
            review = client_session.post(
                "/api/reviews/", {"id_budget": budget.pk, "rating": 4}, format="json"
            )
        assert review.status_code == 201
        [to_workshop] = for_workshop(ready_workshop)
        assert to_workshop.title == "Nova avaliação recebida"
        assert "4 estrelas" in to_workshop.message
        assert to_workshop.url == "w-reviews.html"

        with commit():
            response = ready_workshop_session.post(
                f"/api/workshop/reviews/{review.json()['id']}/response/",
                {"workshop_response": "Obrigado pela confiança!"},
                format="json",
            )
        assert response.status_code == 200
        [to_client] = for_client(client_account)
        assert to_client.title == "A oficina respondeu à sua avaliação"
        assert "Obrigado pela confiança!" in to_client.message
        assert to_client.url == f"attendance.html?id={attendance.pk}"


@pytest.mark.django_db
class TestChatEvents:
    @pytest.fixture
    def chat(self, client_account, ready_workshop):
        client_account.name = "Bruno Costa"
        client_account.save(update_fields=["name"])
        return ChatFactory(client=client_account, workshop=ready_workshop)

    def send(self, session, chat, content, commit):
        with commit():
            response = session.post(
                f"/api/chats/{chat.pk}/messages/", {"content": content}, format="json"
            )
        assert response.status_code == 201
        return response

    def test_five_messages_make_one_unread_notification(
        self, client_session, ready_workshop, chat, commit
    ):
        for n in range(1, 6):
            self.send(client_session, chat, f"Mensagem {n}", commit)

        [notification] = for_workshop(ready_workshop)
        assert notification.read_status is False
        assert notification.title == "5 novas mensagens de Bruno C."
        assert notification.message == "Mensagem 5"
        assert notification.url == f"chat.html?id={chat.pk}"

    def test_first_message_title(
        self, ready_workshop_session, client_account, chat, commit
    ):
        self.send(ready_workshop_session, chat, "Seu carro está pronto", commit)

        [notification] = for_client(client_account)
        assert notification.title == f"Nova mensagem de {chat.workshop.name_fantasy}"
        assert notification.message == "Seu carro está pronto"

    def test_reading_the_chat_reads_its_notification_and_restarts_grouping(
        self, client_session, ready_workshop_session, ready_workshop, chat, commit
    ):
        self.send(client_session, chat, "Oi", commit)
        self.send(client_session, chat, "Tudo bem?", commit)

        assert (
            ready_workshop_session.post(f"/api/chats/{chat.pk}/read/").status_code
            == 204
        )
        first = for_workshop(ready_workshop).get()
        assert first.read_status is True

        self.send(client_session, chat, "Ainda aí?", commit)

        notifications = list(for_workshop(ready_workshop))
        assert len(notifications) == 2
        assert (notifications[1].read_status, notifications[1].title) == (
            False,
            "Nova mensagem de Bruno C.",
        )

    def test_sender_is_never_notified(
        self, client_session, client_account, chat, commit
    ):
        self.send(client_session, chat, "Oi", commit)

        assert not for_client(client_account).exists()

    def test_long_message_preview_is_trimmed(
        self, client_session, ready_workshop, chat, commit
    ):
        self.send(client_session, chat, "palavra " * 60, commit)

        message = for_workshop(ready_workshop).get().message
        assert len(message) <= 140 and message.endswith("…")

    def test_chat_of_other_pair_is_untouched(
        self, client_session, ready_workshop, chat, commit
    ):
        other_chat = ChatFactory(client=ClientFactory(), workshop=ready_workshop)
        NotificationFactory(
            client=None, workshop=ready_workshop, url=f"chat.html?id={other_chat.pk}"
        )

        self.send(client_session, chat, "Oi", commit)

        assert for_workshop(ready_workshop).filter(read_status=False).count() == 2
        assert Chat.objects.count() == 2


# ------------------------------------------------------- rotina de expiração


def _expire_now(budget):
    """Põe a validade no passado sem passar pelas regras de edição (simula o tempo)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE budget DISABLE TRIGGER USER")
        try:
            cursor.execute(
                "UPDATE budget SET date_creation = %s, date_validity = %s WHERE id_budget = %s",
                [
                    timezone.now() - timedelta(days=3),
                    timezone.now() - timedelta(days=1),
                    budget.pk,
                ],
            )
        finally:
            cursor.execute("ALTER TABLE budget ENABLE TRIGGER USER")


@pytest.mark.django_db
class TestExpiredBudgetEvent:
    def test_client_is_notified_once_when_the_job_expires_a_sent_budget(
        self, client_account, flow, commit
    ):
        attendance, budget = flow.waiting()
        _expire_now(budget)

        with commit():
            call_command("run_expiration_jobs", stdout=StringIO())
        with commit():
            call_command("run_expiration_jobs", stdout=StringIO())

        budget.refresh_from_db()
        assert budget.status_budget == "expired"
        [notification] = for_client(client_account)
        assert notification.title == "Orçamento expirado"
        assert notification.url == f"attendance.html?id={attendance.pk}"

    def test_budget_never_sent_expires_silently(self, client_account, flow, commit):
        attendance, budget = flow.budgeted()
        _expire_now(budget)

        with commit():
            call_command("run_expiration_jobs", stdout=StringIO())

        assert Budget.objects.get(pk=budget.pk).status_budget == "expired"
        assert not for_client(client_account).exists()


# ------------------------------------------------- eventos sem rota ainda (Fase 5)


@pytest.mark.django_db
def test_service_request_decision_event_for_moderation(ready_workshop, commit):
    from apps.core.tests.factories import WorkshopServiceFactory

    service = WorkshopServiceFactory(
        workshop=ready_workshop,
        service=None,
        name_local="Polimento",
        status_solicitation="pending",
        suggested_category_id=1,
    )
    service.motivation_rejection = "Já existe no catálogo."

    with commit():
        events.service_request_decided(service, approved=True)
        events.service_request_decided(service, approved=False)

    approved, rejected = for_workshop(ready_workshop)
    assert (approved.title, approved.url) == ("Serviço aprovado", "w-services.html")
    assert rejected.title == "Serviço não aprovado"
    assert rejected.message.endswith("Motivo: Já existe no catálogo.")


@pytest.mark.django_db
def test_notify_rejects_unknown_role():
    with pytest.raises(ValueError):
        notify("admin", 1, "x", "y")


def test_brl_format():
    from decimal import Decimal

    assert events.brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert events.brl(Decimal("0")) == "R$ 0,00"
