"""BE-027 (não enumeração, conta bloqueada) e BE-033 (429 e bloqueio progressivo)."""

import logging
import time
from unittest import mock

import pytest
from apps.accounts.models import AccountStatus, Client
from apps.core.tests.factories import ClientFactory
from apps.core.throttles import LoginRateThrottle
from django.contrib.auth import hashers
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient

PASSWORD = "SenhaTeste123"
URL = "/api/auth/login/"


@pytest.fixture
def account(db):
    return ClientFactory(email="ana@example.com", password_hash=make_password(PASSWORD))


def login(api, email="ana@example.com", password=PASSWORD, ip="10.0.0.1"):
    return api.post(
        URL,
        {"role": "client", "email": email, "password": password},
        format="json",
        REMOTE_ADDR=ip,
    )


@pytest.fixture
def no_rate_limit(monkeypatch):
    """Isola o bloqueio progressivo do limite fixo de 5/min."""
    monkeypatch.setitem(LoginRateThrottle.THROTTLE_RATES, "login", "1000/min")


# ---------------------------------------------------------------- BE-027


@pytest.mark.django_db
class TestNonEnumeration:
    def test_unknown_email_and_wrong_password_look_the_same(self, api_client, account):
        unknown = login(api_client, email="nao.existe@example.com")
        wrong = login(api_client, password="SenhaErrada000")

        assert unknown.status_code == wrong.status_code == 401
        assert (
            unknown.json() == wrong.json() == {"detail": "E-mail ou senha incorretos."}
        )

    def test_unknown_email_still_runs_a_password_hash_check(self, api_client, account):
        """Tempo comparável: e-mail inexistente também paga uma verificação de hash."""
        with mock.patch(
            "apps.accounts.services.check_password", wraps=hashers.check_password
        ) as spy:
            login(api_client, email="nao.existe@example.com")

        assert spy.call_count == 1

    def test_wrong_password_on_blocked_account_does_not_reveal_status(
        self, api_client, account
    ):
        Client.objects.filter(pk=account.pk).update(status=AccountStatus.BLOCKED)

        response = login(api_client, password="SenhaErrada000")

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("status", "message"),
        [
            (AccountStatus.BLOCKED, "Conta bloqueada. Entre em contato com o suporte."),
            (
                AccountStatus.INACTIVE,
                "Conta desativada. Entre em contato com o suporte.",
            ),
        ],
    )
    def test_correct_password_on_non_active_account_is_403(
        self, api_client, account, status, message
    ):
        Client.objects.filter(pk=account.pk).update(status=status)

        response = login(api_client)

        assert response.status_code == 403
        assert response.json() == {"detail": message}
        assert api_client.get("/api/auth/me/").status_code == 401

    def test_attempts_are_logged_with_masked_email(self, api_client, account, caplog):
        with caplog.at_level(logging.INFO, logger="sam.auth"):
            login(api_client, password="SenhaErrada000")
            login(api_client)

        events = [
            (r.getMessage(), getattr(r, "success", None), getattr(r, "email", ""))
            for r in caplog.records
        ]
        assert ("auth.login", False, "a**@example.com") in events
        assert ("auth.login", True, "a**@example.com") in events
        assert all(PASSWORD not in r.getMessage() for r in caplog.records)


# -------------------------------------------------------- BE-033: limite fixo


@pytest.mark.django_db
def test_sixth_invalid_login_in_a_minute_gets_429(account):
    api = APIClient()
    statuses = [login(api, password="SenhaErrada000").status_code for _ in range(6)]

    assert statuses == [401] * 5 + [429]


@pytest.mark.django_db
def test_429_message_is_in_portuguese_with_retry_after(account):
    api = APIClient()
    for _ in range(5):
        login(api, password="SenhaErrada000")

    response = login(api, password="SenhaErrada000")

    assert response.status_code == 429
    wait = int(response["Retry-After"])
    assert response.json() == {
        "detail": f"Muitas requisições em pouco tempo. Tente novamente em {wait} segundos."
    }


@pytest.mark.django_db
def test_rate_limit_is_per_ip_and_email(account):
    api = APIClient()
    for _ in range(5):
        login(api, password="SenhaErrada000", ip="10.0.0.1")

    assert login(api, password="SenhaErrada000", ip="10.0.0.1").status_code == 429
    assert login(api, ip="10.0.0.2").status_code == 200
    assert login(api, email="outra@example.com", ip="10.0.0.1").status_code == 401


# -------------------------------------------- BE-033: bloqueio progressivo


@pytest.mark.django_db
@pytest.mark.usefixtures("no_rate_limit")
class TestProgressiveLockout:
    def test_lock_blocks_even_the_correct_password_then_expires(self, account):
        api = APIClient()
        for _ in range(5):
            assert login(api, password="SenhaErrada000").status_code == 401

        locked = login(api)
        assert locked.status_code == 429
        assert int(locked["Retry-After"]) == 60
        assert locked.json() == {
            "detail": "Muitas tentativas de login sem sucesso. Tente novamente em 60 segundos."
        }

        with mock.patch("time.time", return_value=time.time() + 61):
            assert login(api).status_code == 200

    def test_lock_doubles_on_each_new_failure(self, account):
        api = APIClient()
        for _ in range(5):
            login(api, password="SenhaErrada000")
        assert int(login(api)["Retry-After"]) == 60

        later = time.time() + 61
        with mock.patch("time.time", return_value=later):
            assert login(api, password="SenhaErrada000").status_code == 401
            assert int(login(api)["Retry-After"]) == 120

    def test_success_resets_the_counter(self, account):
        api = APIClient()
        for _ in range(4):
            login(api, password="SenhaErrada000")
        assert login(api).status_code == 200
        for _ in range(4):
            assert login(api, password="SenhaErrada000").status_code == 401

        assert login(api).status_code == 200

    def test_other_ip_is_not_locked_by_the_ip_lock(self, account):
        api = APIClient()
        for _ in range(5):
            login(api, password="SenhaErrada000", ip="10.0.0.1")

        assert login(api, ip="10.0.0.1").status_code == 429
        assert login(api, ip="10.0.0.9").status_code == 200

    def test_distributed_attack_locks_the_account(self, account, settings):
        settings.SAM_LOGIN_LOCKOUT = {
            **settings.SAM_LOGIN_LOCKOUT,
            "ACCOUNT_THRESHOLD": 3,
        }
        api = APIClient()
        for n in range(3):
            assert (
                login(api, password="SenhaErrada000", ip=f"10.0.1.{n}").status_code
                == 401
            )

        assert login(api, ip="10.0.2.1").status_code == 429

    def test_lockout_is_logged(self, account, caplog):
        api = APIClient()
        with caplog.at_level(logging.WARNING, logger="sam.auth"):
            for _ in range(5):
                login(api, password="SenhaErrada000")
            login(api)

        reasons = [getattr(r, "reason", None) for r in caplog.records]
        lockouts = [r for r in caplog.records if r.getMessage() == "auth.lockout"]
        assert lockouts and lockouts[0].lock_seconds == 60
        assert "locked" in reasons
