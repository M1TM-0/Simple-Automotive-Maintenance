"""BE-057 (abrir/listar/detalhar) e BE-058 (mensagens, polling e leitura)."""

import threading
from datetime import timedelta

import pytest
from apps.chat.models import Chat, Message
from apps.chat.services import open_chat, send_message
from apps.core.tests.factories import (
    AttendanceFactory,
    ChatFactory,
    ClientFactory,
    MessageFactory,
    PagWorkshopFactory,
)
from apps.core.throttles import MessageRateThrottle
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

URL = "/api/chats/"


@pytest.fixture
def workshop(db):
    return PagWorkshopFactory().workshop


@pytest.fixture
def chat(client_account, workshop):
    return ChatFactory(client=client_account, workshop=workshop)


@pytest.fixture
def workshop_api(account_session, workshop):
    return account_session(workshop, "workshop")


# ------------------------------------------------------------------ BE-057


@pytest.mark.django_db
class TestOpenListDetail:
    def test_open_is_idempotent_and_returns_only_the_workshop(
        self, client_session, workshop
    ):
        first = client_session.post(f"{URL}{workshop.pk}/open/")
        second = client_session.post(f"{URL}{workshop.pk}/open/")

        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["id"] == second.json()["id"]
        body = first.json()
        assert body["workshop"]["id"] == workshop.pk
        assert body["workshop"]["name_fantasy"] == workshop.name_fantasy
        assert "client" not in body
        assert (
            body["last_message"],
            body["unread_count"],
            body["open_attendance"],
        ) == (None, 0, None)
        assert Chat.objects.count() == 1

    def test_workshop_cannot_open(self, workshop_api, workshop):
        assert workshop_api.post(f"{URL}{workshop.pk}/open/").status_code == 403

    @pytest.mark.parametrize("status", ["blocked", "inactive"])
    def test_unavailable_or_missing_workshop_is_404(self, client_session, status):
        blocked = PagWorkshopFactory(workshop__status=status).workshop
        assert client_session.post(f"{URL}{blocked.pk}/open/").status_code == 404
        assert client_session.post(f"{URL}999999/open/").status_code == 404

    def test_list_for_each_side(
        self, client_session, workshop_api, chat, client_account
    ):
        MessageFactory(chat=chat, sender_client=client_account, content="Olá")
        MessageFactory(
            chat=chat,
            sender_client=None,
            sender_workshop=chat.workshop,
            content="Oi, tudo bem?",
        )
        attendance = AttendanceFactory(client=client_account, workshop=chat.workshop)

        mine = client_session.get(URL).json()["results"][0]
        theirs = workshop_api.get(URL).json()["results"][0]

        assert mine["workshop"]["id"] == chat.workshop_id and "client" not in mine
        assert theirs["client"] == {
            "id": client_account.pk,
            "name": client_account.name,
            "photo_profile": None,
        }
        assert "workshop" not in theirs
        assert mine["last_message"]["content"] == "Oi, tudo bem?"
        assert mine["last_message"]["sender"] == "workshop"
        assert (mine["unread_count"], theirs["unread_count"]) == (1, 1)
        assert mine["open_attendance"] == {
            "id": attendance.pk,
            "status_attendance": "requested",
        }

    def test_list_is_ordered_by_last_message(self, client_session, client_account):
        old, recent, empty = (ChatFactory(client=client_account) for _ in range(3))
        Message.objects.create(
            chat=old,
            sender_client=client_account,
            content="a",
            date_sent=timezone.now() - timedelta(days=2),
        )
        Message.objects.create(
            chat=recent,
            sender_client=client_account,
            content="b",
            date_sent=timezone.now() - timedelta(hours=1),
        )

        ids = [row["id"] for row in client_session.get(URL).json()["results"]]

        assert ids == [recent.pk, old.pk, empty.pk]

    def test_list_query_count_is_constant(self, client_session, client_account):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                assert client_session.get(URL).status_code == 200
            return len(ctx.captured_queries)

        for _ in range(2):
            MessageFactory(
                chat=ChatFactory(client=client_account), sender_client=client_account
            )
        two = count()
        for _ in range(18):
            MessageFactory(
                chat=ChatFactory(client=client_account), sender_client=client_account
            )
        assert count() == two

    def test_chat_of_another_pair_is_404(self, client_session, workshop_api):
        other = ChatFactory()
        for api in (client_session, workshop_api):
            assert api.get(f"{URL}{other.pk}/").status_code == 404
            assert api.get(f"{URL}{other.pk}/messages/").status_code == 404
            assert (
                api.post(
                    f"{URL}{other.pk}/messages/", {"content": "x"}, format="json"
                ).status_code
                == 404
            )
            assert api.post(f"{URL}{other.pk}/read/").status_code == 404

    def test_access_matrix(self, api_client, admin_session):
        assert api_client.get(URL).status_code == 401
        assert admin_session.get(URL).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_concurrent_open_creates_a_single_chat():
    client = ClientFactory()
    workshop = PagWorkshopFactory().workshop
    barrier = threading.Barrier(2)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            chat, _ = open_chat(client.pk, workshop.pk)
            results.append(chat.pk)
        except Exception as exc:  # pragma: no cover - falha aparece no assert
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 2 and results[0] == results[1]
    assert Chat.objects.filter(client=client, workshop=workshop).count() == 1


# ------------------------------------------------------------------ BE-058


@pytest.mark.django_db
class TestMessages:
    def url(self, chat):
        return f"{URL}{chat.pk}/messages/"

    @pytest.mark.parametrize("content", ["", "   ", "x" * 2001])
    def test_invalid_content_is_400(self, client_session, chat, content):
        response = client_session.post(
            self.url(chat), {"content": content}, format="json"
        )
        assert response.status_code == 400
        assert "content" in response.json()

    def test_send_uses_session_sender(
        self, client_session, workshop_api, chat, client_account
    ):
        sent = client_session.post(
            self.url(chat),
            {"content": "x" * 2000, "id_workshop": chat.workshop_id},
            format="json",
        )
        reply = workshop_api.post(
            self.url(chat), {"content": "Pode trazer amanhã"}, format="json"
        )

        assert sent.status_code == 201
        assert (
            sent.json()["sender"],
            sent.json()["mine"],
            sent.json()["status_message"],
        ) == ("client", True, "sent")
        assert reply.json()["sender"] == "workshop"
        message = Message.objects.get(pk=sent.json()["id"])
        assert (message.sender_client_id, message.sender_workshop_id) == (
            client_account.pk,
            None,
        )

    @pytest.mark.parametrize("status", ["closed", "archived"])
    def test_closed_chat_is_403(self, client_session, chat, status):
        Chat.objects.filter(pk=chat.pk).update(status_chat=status)
        response = client_session.post(self.url(chat), {"content": "oi"}, format="json")
        assert response.status_code == 403
        assert "encerrada" in response.json()["detail"]

    def test_date_sent_is_the_insert_instant(self, chat, client_account):
        with connection.cursor() as cursor:
            cursor.execute("SELECT now()")
            transaction_start = cursor.fetchone()[0]
            cursor.execute("SELECT pg_sleep(0.05)")
        message = send_message(chat, "client", client_account.pk, "oi")
        assert message.date_sent > transaction_start

    def test_after_is_inclusive_and_chronological(
        self, client_session, chat, client_account
    ):
        base = timezone.now() - timedelta(minutes=10)
        a, b, c = (
            Message.objects.create(
                chat=chat,
                sender_client=client_account,
                content=t,
                date_sent=base + timedelta(seconds=i),
            )
            for i, t in enumerate("abc")
        )

        rows = client_session.get(
            self.url(chat), {"after": b.date_sent.isoformat()}
        ).json()["results"]

        assert [row["id"] for row in rows] == [b.pk, c.pk]
        assert a.pk not in [row["id"] for row in rows]

    def test_without_after_returns_latest_page_in_order(
        self, client_session, chat, client_account
    ):
        base = timezone.now() - timedelta(hours=1)
        created = [
            Message.objects.create(
                chat=chat,
                sender_client=client_account,
                content=str(i),
                date_sent=base + timedelta(seconds=i),
            )
            for i in range(25)
        ]

        body = client_session.get(self.url(chat)).json()

        assert body["count"] == 25
        assert [row["id"] for row in body["results"]] == [m.pk for m in created[5:]]
        older = client_session.get(self.url(chat), {"page": 2}).json()["results"]
        assert [row["id"] for row in older] == [m.pk for m in created[:5]]

    def test_invalid_after_is_400(self, client_session, chat):
        response = client_session.get(self.url(chat), {"after": "ontem"})
        assert response.status_code == 400
        assert "after" in response.json()

    def test_reading_marks_counterpart_as_delivered_then_read(
        self, client_session, workshop_api, chat, client_account
    ):
        mine = MessageFactory(chat=chat, sender_client=client_account)
        theirs = MessageFactory(
            chat=chat, sender_client=None, sender_workshop=chat.workshop
        )

        client_session.get(
            self.url(chat)
        )  # o cliente lê: só a mensagem da oficina vira delivered
        assert [
            Message.objects.get(pk=m.pk).status_message for m in (mine, theirs)
        ] == ["sent", "delivered"]

        assert workshop_api.post(f"{URL}{chat.pk}/read/").status_code == 204
        assert [
            Message.objects.get(pk=m.pk).status_message for m in (mine, theirs)
        ] == ["read", "delivered"]

    def test_send_is_rate_limited_but_reads_are_not(
        self, client_session, chat, monkeypatch
    ):
        monkeypatch.setitem(MessageRateThrottle.THROTTLE_RATES, "message", "2/min")
        codes = [
            client_session.post(
                self.url(chat), {"content": "oi"}, format="json"
            ).status_code
            for _ in range(3)
        ]
        assert codes == [201, 201, 429]
        assert client_session.get(self.url(chat)).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_late_commit_is_not_lost_by_polling():
    """Transação A começa antes de B, mas grava depois de B confirmar. Com o DEFAULT
    CURRENT_TIMESTAMP (início da transação) a mensagem de A ficaria com horário
    anterior ao de B e o polling `after=<B>` a perderia; com clock_timestamp() não."""
    from django.db import transaction

    chat = ChatFactory()
    a_started, b_committed = threading.Event(), threading.Event()
    late = {}

    def slow_sender():
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")  # a transação já começou
                a_started.set()
                b_committed.wait(timeout=5)
                late["message"] = send_message(
                    chat, "workshop", chat.workshop_id, "A (atrasada)"
                )
        finally:
            connections.close_all()

    thread = threading.Thread(target=slow_sender)
    thread.start()
    a_started.wait(timeout=5)
    fast = send_message(chat, "client", chat.client_id, "B (rápida)")
    b_committed.set()
    thread.join()

    assert late["message"].date_sent > fast.date_sent
    polled = Message.objects.filter(
        chat=chat, date_sent__gte=fast.date_sent
    ).values_list("pk", flat=True)
    assert set(polled) == {fast.pk, late["message"].pk}
