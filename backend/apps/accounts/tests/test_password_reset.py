"""BE-032: recuperação e redefinição de senha por e-mail."""

import logging
import re
import time
from unittest import mock

import pytest
from apps.accounts.models import AccountStatus, Client
from apps.accounts.tokens import make_password_reset_token
from apps.core.tests.factories import ClientFactory, PagWorkshopFactory
from django.contrib.auth.hashers import check_password, make_password
from django.core import mail, signing

PASSWORD = "SenhaTeste123"
NEW_PASSWORD = "NovaSenha456"
REQUEST_URL = "/api/auth/password-reset/"
CONFIRM_URL = "/api/auth/password-reset/confirm/"


@pytest.fixture(autouse=True)
def outbox_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.FRONTEND_BASE_URL = "http://localhost:5500"


@pytest.fixture
def account(db):
    return ClientFactory(email="ana@example.com", password_hash=make_password(PASSWORD))


def token_from_outbox():
    match = re.search(r"forgot-password\.html\?token=([^\s\"<]+)", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


def confirm(api, token, password=NEW_PASSWORD, key="password"):
    return api.post(CONFIRM_URL, {"token": token, key: password}, format="json")


@pytest.mark.django_db
class TestRequest:
    def test_existing_and_unknown_emails_get_identical_responses(
        self, api_client, account
    ):
        existing = api_client.post(
            REQUEST_URL, {"role": "client", "email": "ANA@example.com"}, format="json"
        )
        unknown = api_client.post(
            REQUEST_URL,
            {"role": "client", "email": "nao.existe@example.com"},
            format="json",
        )

        assert existing.status_code == unknown.status_code == 204
        assert existing.content == unknown.content == b""
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [account.email]
        assert (
            "http://localhost:5500/forgot-password.html?token=" in mail.outbox[0].body
        )

    def test_role_limits_the_lookup(self, api_client, account):
        api_client.post(
            REQUEST_URL, {"role": "workshop", "email": account.email}, format="json"
        )
        assert len(mail.outbox) == 0

    def test_without_role_both_profiles_are_tried(self, api_client, account):
        PagWorkshopFactory(workshop__email=account.email)

        api_client.post(REQUEST_URL, {"email": account.email}, format="json")

        assert len(mail.outbox) == 2

    @pytest.mark.parametrize("status", [AccountStatus.BLOCKED, AccountStatus.INACTIVE])
    def test_non_active_account_gets_no_email(self, api_client, account, status):
        Client.objects.filter(pk=account.pk).update(status=status)

        response = api_client.post(
            REQUEST_URL, {"role": "client", "email": account.email}, format="json"
        )

        assert response.status_code == 204
        assert len(mail.outbox) == 0

    def test_email_failure_is_logged_and_response_stays_generic(
        self, api_client, account, caplog
    ):
        with (
            mock.patch(
                "apps.accounts.services.send_password_reset_email",
                side_effect=OSError("smtp fora"),
            ),
            caplog.at_level(logging.ERROR, logger="sam.auth"),
        ):
            response = api_client.post(
                REQUEST_URL, {"role": "client", "email": account.email}, format="json"
            )

        assert response.status_code == 204
        assert any(
            record.getMessage() == "auth.password_reset_email_failed"
            for record in caplog.records
        )

    def test_invalid_email_is_400(self, api_client):
        response = api_client.post(REQUEST_URL, {"email": "sem-arroba"}, format="json")
        assert response.status_code == 400
        assert "email" in response.json()


@pytest.mark.django_db
class TestConfirm:
    def test_full_flow_changes_password(self, api_client, account):
        api_client.post(
            REQUEST_URL, {"role": "client", "email": account.email}, format="json"
        )

        response = confirm(api_client, token_from_outbox())

        assert response.status_code == 204
        account.refresh_from_db()
        assert check_password(NEW_PASSWORD, account.password_hash)

    def test_token_is_single_use(self, api_client, account):
        token = make_password_reset_token("client", account)
        assert confirm(api_client, token).status_code == 204

        reused = confirm(api_client, token, password="OutraSenha789")

        assert reused.status_code == 400
        assert "inválido" in reused.json()["detail"]
        account.refresh_from_db()
        assert check_password(NEW_PASSWORD, account.password_hash)

    def test_token_older_than_one_hour_is_rejected(self, api_client, account):
        with mock.patch("time.time", return_value=time.time() - 3601):
            token = make_password_reset_token("client", account)

        response = confirm(api_client, token)

        assert response.status_code == 400
        assert "expirou" in response.json()["detail"]
        account.refresh_from_db()
        assert check_password(PASSWORD, account.password_hash)

    def test_token_just_under_one_hour_is_accepted(self, api_client, account):
        with mock.patch("time.time", return_value=time.time() - 3500):
            token = make_password_reset_token("client", account)

        assert confirm(api_client, token).status_code == 204

    @pytest.mark.parametrize(
        "token",
        [
            "lixo",
            signing.dumps({"r": "client", "i": 1, "f": "x"}, salt="outro-sal"),
            signing.dumps({"r": "admin", "i": 1, "f": "x"}, salt="sam.password-reset"),
            signing.dumps(
                {"r": "client", "i": "1", "f": "x"}, salt="sam.password-reset"
            ),
            signing.dumps(["client", 1], salt="sam.password-reset"),
        ],
    )
    def test_tampered_tokens_are_rejected(self, api_client, account, token):
        response = confirm(api_client, token)

        assert response.status_code == 400
        assert "detail" in response.json()

    def test_password_change_invalidates_pending_token(self, api_client, account):
        token = make_password_reset_token("client", account)
        Client.objects.filter(pk=account.pk).update(
            password_hash=make_password("Trocada123")
        )

        assert confirm(api_client, token).status_code == 400

    def test_blocked_account_cannot_reset(self, api_client, account):
        token = make_password_reset_token("client", account)
        Client.objects.filter(pk=account.pk).update(status=AccountStatus.BLOCKED)

        assert confirm(api_client, token).status_code == 400

    def test_weak_password_is_400_on_password_field(self, api_client, account):
        response = confirm(
            api_client,
            make_password_reset_token("client", account),
            password="12345678",
        )

        assert response.status_code == 400
        assert response.json() == {"password": ["Use letras e números."]}

    def test_new_password_alias_is_accepted(self, api_client, account):
        token = make_password_reset_token("client", account)
        assert confirm(api_client, token, key="new_password").status_code == 204

    def test_reset_invalidates_open_sessions(
        self, api_client, account, account_session
    ):
        session = account_session(account, "client")
        assert session.get("/api/auth/me/").status_code == 200

        confirm(api_client, make_password_reset_token("client", account))

        assert session.get("/api/auth/me/").status_code == 401

    def test_token_payload_does_not_expose_the_hash(self, account):
        token = make_password_reset_token("client", account)
        payload = signing.loads(token, salt="sam.password-reset")
        assert payload["f"] not in account.password_hash
        assert len(payload["f"]) == 64
