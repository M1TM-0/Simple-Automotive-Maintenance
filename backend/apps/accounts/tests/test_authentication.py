"""BE-025 / BE-030: sessão de dois perfis, CSRF, 401 × 403 e invalidação de sessão."""

import pytest
from apps.accounts.models import AccountStatus, Client, Workshop
from apps.accounts.sessions import SESSION_ID, SESSION_PASSWORD, SESSION_ROLE
from apps.core.tests.factories import ClientFactory, PagWorkshopFactory
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient

PASSWORD = "SenhaTeste123"


def csrf_client():
    """Cliente HTTP que aplica CSRF como o navegador (cookie + X-CSRFToken)."""
    client = APIClient(enforce_csrf_checks=True)
    assert client.get("/api/auth/me/").status_code == 401
    return client


def csrf(client):
    return client.cookies["csrftoken"].value


def login(client, role, email, password=PASSWORD):
    return client.post(
        "/api/auth/login/",
        {"role": role, "email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
    )


# ---------------------------------------------------------- 401 × 403 (P-01)


@pytest.mark.django_db
class TestUnauthenticatedGets401:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("get", "/api/workshop/services/"),
            ("post", "/api/workshop/services/"),
            ("patch", "/api/me/"),
            ("post", "/api/me/password/"),
            ("post", "/api/auth/logout/"),
        ],
    )
    def test_visitor_on_protected_endpoint(self, api_client, method, url):
        response = getattr(api_client, method)(url, {}, format="json")

        assert response.status_code == 401
        assert response["WWW-Authenticate"] == "Session"
        assert "detail" in response.json()

    def test_wrong_profile_still_gets_403(self, client_session):
        response = client_session.get("/api/workshop/services/")

        assert response.status_code == 403
        assert response.json() == {"detail": "Esta ação é exclusiva para oficinas."}

    def test_auth_me_keeps_401_with_csrf_cookie(self, api_client):
        response = api_client.get("/api/auth/me/")

        assert response.status_code == 401
        assert "csrftoken" in response.cookies


# ------------------------------------------------------- dois perfis (P-08)


@pytest.mark.django_db
def test_same_email_logs_in_as_client_and_as_workshop():
    email = "mesmo.email@example.com"
    client_account = ClientFactory(email=email, password_hash=make_password(PASSWORD))
    workshop_account = PagWorkshopFactory(
        workshop__email=email, workshop__password_hash=make_password(PASSWORD)
    ).workshop

    as_client = csrf_client()
    as_workshop = csrf_client()
    assert login(as_client, "client", email).status_code == 200
    assert login(as_workshop, "workshop", email).status_code == 200

    assert (
        as_client.cookies["sessionid"].value != as_workshop.cookies["sessionid"].value
    )

    me_client = as_client.get("/api/auth/me/").json()["user"]
    me_workshop = as_workshop.get("/api/auth/me/").json()["user"]
    assert (me_client["role"], me_client["id"]) == ("client", client_account.pk)
    assert (me_workshop["role"], me_workshop["id"]) == ("workshop", workshop_account.pk)


@pytest.mark.django_db
def test_login_rotates_session_key_and_csrf_token():
    account = ClientFactory(password_hash=make_password(PASSWORD))
    client = csrf_client()
    # Sessão anônima pré-existente (tentativa de fixação de sessão).
    session = client.session
    session["qualquer"] = "coisa"
    session.save()
    client.cookies["sessionid"] = session.session_key
    old_session, old_csrf = session.session_key, csrf(client)

    assert login(client, "client", account.email).status_code == 200

    assert client.cookies["sessionid"].value != old_session
    assert csrf(client) != old_csrf
    stored = client.session
    assert "qualquer" not in stored
    assert (stored[SESSION_ROLE], stored[SESSION_ID]) == ("client", account.pk)
    assert stored[SESSION_PASSWORD]


# --------------------------------------------------------------- CSRF (P-08)


@pytest.mark.django_db
class TestCsrfOnAuthenticatedRequests:
    def test_post_without_csrf_header_is_403_and_session_survives(self):
        account = ClientFactory(password_hash=make_password(PASSWORD))
        client = csrf_client()
        login(client, "client", account.email)

        response = client.post("/api/auth/logout/")

        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
        assert client.get("/api/auth/me/").status_code == 200

    def test_post_with_csrf_header_is_accepted(self):
        account = ClientFactory(password_hash=make_password(PASSWORD))
        client = csrf_client()
        login(client, "client", account.email)

        response = client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=csrf(client))

        assert response.status_code == 204

    def test_public_post_without_csrf_gets_json_403(self):
        client = csrf_client()

        response = client.post(
            "/api/auth/login/",
            {"role": "client", "email": "x@example.com", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 403
        assert response["Content-Type"].startswith("application/json")
        assert "CSRF" in response.json()["detail"]


# ------------------------------------------ sessão recusada (BE-025, P-03)


@pytest.mark.django_db
class TestSessionIsRejected:
    @pytest.mark.parametrize("status", [AccountStatus.BLOCKED, AccountStatus.INACTIVE])
    def test_session_of_non_active_account(self, account_session, status):
        account = ClientFactory()
        api = account_session(account, "client")
        assert api.get("/api/auth/me/").status_code == 200

        Client.objects.filter(pk=account.pk).update(status=status)

        assert api.get("/api/auth/me/").status_code == 401
        # A sessão foi descartada: reativar a conta não a ressuscita.
        Client.objects.filter(pk=account.pk).update(status=AccountStatus.ACTIVE)
        assert api.get("/api/auth/me/").status_code == 401

    def test_session_after_password_changed_elsewhere(self, account_session):
        account = PagWorkshopFactory().workshop
        api = account_session(account, "workshop")
        assert api.get("/api/auth/me/").status_code == 200

        Workshop.objects.filter(pk=account.pk).update(
            password_hash=make_password("OutraSenha987")
        )

        assert api.get("/api/auth/me/").status_code == 401

    def test_deleted_account(self, account_session):
        account = ClientFactory()
        api = account_session(account, "client")
        Client.objects.filter(pk=account.pk).delete()

        assert api.get("/api/auth/me/").status_code == 401

    @pytest.mark.parametrize(
        "data",
        [
            {SESSION_ROLE: "admin", SESSION_ID: 1},
            {SESSION_ROLE: "client", SESSION_ID: "abc"},
            {SESSION_ROLE: "client", SESSION_ID: True},
            {SESSION_ROLE: "client", SESSION_ID: -1},
            {SESSION_ROLE: "client"},
            {"role": "client", "id": 1},  # chaves legadas não autenticam mais
        ],
    )
    def test_tampered_or_incomplete_session(self, data):
        ClientFactory()
        client = APIClient()
        session = client.session
        session.update(data)
        session.save()
        client.cookies["sessionid"] = session.session_key

        assert client.get("/api/auth/me/").status_code == 401

    def test_session_without_fingerprint(self):
        account = ClientFactory()
        client = APIClient()
        session = client.session
        session.update({SESSION_ROLE: "client", SESSION_ID: account.pk})
        session.save()
        client.cookies["sessionid"] = session.session_key

        assert client.get("/api/auth/me/").status_code == 401


# ------------------------------------------------------- admin Django (DP-03)


@pytest.mark.django_db
class TestDjangoUsers:
    def test_staff_is_recognized_as_admin(self, admin_session):
        user = admin_session.get("/api/auth/me/").json()["user"]
        assert user["role"] == "admin"

    def test_non_staff_django_user_is_anonymous_for_the_api(self, django_user_model):
        user = django_user_model.objects.create_user("comum", "c@exemplo.com", "x" * 12)
        client = APIClient()
        client.force_login(user)

        assert client.get("/api/auth/me/").status_code == 401
        assert client.patch("/api/me/", {}, format="json").status_code == 401

    def test_admin_cannot_use_account_routes(self, admin_session):
        response = admin_session.patch("/api/me/", {"name": "x"}, format="json")

        assert response.status_code == 403
        assert response.json() == {
            "detail": "Esta ação é exclusiva para clientes e oficinas."
        }
