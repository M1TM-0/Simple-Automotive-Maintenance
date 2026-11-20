"""BE-033: limites de mensagens/polling e bloqueio progressivo (unidade)."""

import uuid

import pytest
from apps.accounts.principal import Principal
from apps.core.tests.factories import ClientFactory
from apps.core.throttles import (
    MessageRateThrottle,
    PollingRateThrottle,
    ProgressiveLockout,
)
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ChatMessagesProbe(APIView):
    """Como será `GET/POST /chats/{id}/messages/` (BE-058)."""

    permission_classes = [AllowAny]
    throttle_classes = [MessageRateThrottle, PollingRateThrottle]

    def get(self, request):
        return Response({"results": []})

    def post(self, request):
        return Response({"ok": True}, status=201)


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(MessageRateThrottle, "timer", fake)
    monkeypatch.setattr(PollingRateThrottle, "timer", fake)
    return fake


@pytest.fixture
def rates(monkeypatch):
    monkeypatch.setitem(MessageRateThrottle.THROTTLE_RATES, "message", "30/min")
    monkeypatch.setitem(PollingRateThrottle.THROTTLE_RATES, "polling", "120/min")


def call(method, user):
    factory = APIRequestFactory()
    request = getattr(factory, method)("/api/chats/1/messages/", {}, format="json")
    force_authenticate(request, user=user)
    return ChatMessagesProbe.as_view()(request)


@pytest.mark.django_db
@pytest.mark.usefixtures("rates")
class TestChatThrottles:
    def test_polling_every_5s_for_10_minutes_is_never_throttled(self, clock):
        user = Principal(ClientFactory(), "client")
        statuses = set()
        for _ in range(120):  # 10 min a cada 5 s
            statuses.add(call("get", user).status_code)
            clock.advance(5)

        assert statuses == {200}

    def test_polling_burst_is_eventually_throttled(self, clock):
        user = Principal(ClientFactory(), "client")
        statuses = [call("get", user).status_code for _ in range(121)]

        assert statuses[:120] == [200] * 120
        assert statuses[120] == 429

    def test_sending_messages_is_limited_per_user(self, clock):
        sender = Principal(ClientFactory(), "client")
        other = Principal(ClientFactory(), "client")

        statuses = [call("post", sender).status_code for _ in range(31)]

        assert statuses[:30] == [201] * 30
        assert statuses[30] == 429
        assert call("post", other).status_code == 201
        # O limite de envio não atrapalha o polling do mesmo usuário.
        assert call("get", sender).status_code == 200

    def test_reads_do_not_consume_the_send_quota(self, clock):
        user = Principal(ClientFactory(), "client")
        for _ in range(100):
            call("get", user)
            clock.advance(1)

        assert call("post", user).status_code == 201


class TestProgressiveLockout:
    @pytest.fixture
    def lockout(self):
        clock = FakeClock()
        lock = ProgressiveLockout(
            "t",
            threshold=3,
            base_seconds=10,
            max_seconds=35,
            window_seconds=100,
            cache=LocMemCache(
                f"lockout-{uuid.uuid4()}", {}
            ),  # nome único: LocMem compartilha por nome
            timer=clock,
        )
        return lock, clock

    def test_locks_at_threshold_and_doubles_up_to_max(self, lockout):
        lock, clock = lockout
        assert [lock.register_failure("x") for _ in range(2)] == [0, 0]
        assert lock.register_failure("x") == 10
        assert lock.retry_after("x") == 10

        clock.advance(4)
        assert lock.retry_after("x") == 6

        assert [lock.register_failure("x") for _ in range(3)] == [20, 35, 35]

    def test_identifiers_are_independent_and_reset_clears(self, lockout):
        lock, _ = lockout
        for _ in range(3):
            lock.register_failure("x")

        assert lock.retry_after("y") == 0
        lock.reset("x")
        assert lock.retry_after("x") == 0
        assert lock.register_failure("x") == 0

    def test_lock_expires_with_time(self, lockout):
        lock, clock = lockout
        for _ in range(3):
            lock.register_failure("x")

        clock.advance(10)

        assert lock.retry_after("x") == 0
