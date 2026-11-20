import pytest
from apps.accounts.models import (
    AccountStatus,
    Client,
    Workshop,
)
from apps.core.validators import cnpj_check_digits
from django.contrib.auth.hashers import (
    identify_hasher,
    make_password,
)
from rest_framework.test import APIClient

PASSWORD = "SenhaTeste123"


@pytest.fixture
def api_client():
    """
    Cria um cliente HTTP com verificação CSRF habilitada.

    Isso permite testar a proteção CSRF aplicada
    aos endpoints de autenticação.
    """

    return APIClient(enforce_csrf_checks=True)


def get_csrf_token(client):
    """
    Solicita o cookie CSRF antes de executar operações POST.

    O endpoint /auth/me/ deve fornecer o cookie mesmo
    quando não existe uma sessão autenticada.
    """

    response = client.get("/api/auth/me/")

    assert response.status_code == 401
    assert "csrftoken" in client.cookies

    return client.cookies["csrftoken"].value


def make_valid_cnpj():
    """
    Gera um CNPJ com dígitos verificadores válidos.
    """

    base = "123456780001"

    return base + cnpj_check_digits(base)


def make_valid_alphanumeric_cnpj():
    """
    Gera um CNPJ alfanumérico com dígitos verificadores válidos.
    """

    base = "12ABC34501DE"

    return base + cnpj_check_digits(base)


@pytest.mark.django_db
class TestRegisterView:
    def test_register_client_creates_argon2_hash_and_session(self, api_client):
        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/register/",
            {
                "role": "client",
                "name": "Cliente de Teste",
                "email": "cliente.registro@example.com",
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 201

        assert response.data["user"]["role"] == "client"
        assert response.data["user"]["name"] == "Cliente de Teste"

        # Confirma que a senha foi armazenada utilizando Argon2.
        account = Client.objects.get(email="cliente.registro@example.com")

        assert identify_hasher(account.password_hash).algorithm == "argon2"

        # Confirma que o cadastro iniciou uma sessão autenticada.
        me_response = api_client.get("/api/auth/me/")

        assert me_response.status_code == 200
        assert me_response.data["user"]["id"] == account.pk
        assert me_response.data["user"]["role"] == "client"

    def test_register_workshop_creates_account(self, api_client):
        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/register/",
            {
                "role": "workshop",
                "name_fantasy": "Oficina de Teste",
                "name_responsible": "Responsável Teste",
                "cnpj": make_valid_cnpj(),
                "email": "oficina.registro@example.com",
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 201

        assert response.data["user"]["role"] == "workshop"
        assert response.data["user"]["name"] == "Oficina de Teste"

        account = Workshop.objects.get(email="oficina.registro@example.com")

        assert identify_hasher(account.password_hash).algorithm == "argon2"

        # A oficina recém-criada ainda não possui serviços.
        assert response.data["user"]["setup_complete"] is False

    def test_client_and_workshop_can_share_same_email(self, api_client):
        csrf = get_csrf_token(api_client)

        email = "compartilhado@example.com"

        client_response = api_client.post(
            "/api/auth/register/",
            {
                "role": "client",
                "name": "Cliente Compartilhado",
                "email": email,
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        # O cadastro abre sessão e rotaciona o token CSRF (BE-025).
        csrf = api_client.cookies["csrftoken"].value

        workshop_response = api_client.post(
            "/api/auth/register/",
            {
                "role": "workshop",
                "name_fantasy": "Oficina Compartilhada",
                "name_responsible": "Responsável",
                "cnpj": make_valid_cnpj(),
                "email": email,
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert client_response.status_code == 201
        assert workshop_response.status_code == 201

        assert Client.objects.filter(email=email).exists()
        assert Workshop.objects.filter(email=email).exists()

    def test_register_workshop_accepts_alphanumeric_cnpj(self, api_client):
        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/register/",
            {
                "role": "workshop",
                "name_fantasy": "Oficina Alfanumérica",
                "name_responsible": "Responsável Teste",
                "cnpj": "12.abc.345/01de-35",
                "email": "oficina.alfanumerica@example.com",
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 201

        account = Workshop.objects.get(email="oficina.alfanumerica@example.com")

        assert account.cnpj == make_valid_alphanumeric_cnpj()

    def test_register_workshop_rejects_invalid_cnpj(self, api_client):
        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/register/",
            {
                "role": "workshop",
                "name_fantasy": "Oficina Inválida",
                "name_responsible": "Responsável Teste",
                "cnpj": "12345678000182",
                "email": "oficina.cnpj.invalido@example.com",
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "cnpj" in response.data

        assert not Workshop.objects.filter(
            email="oficina.cnpj.invalido@example.com"
        ).exists()


@pytest.mark.django_db
class TestLoginView:
    def create_client(self, email, password=PASSWORD, status=AccountStatus.ACTIVE):
        """
        Cria uma conta de teste com senha previamente armazenada em hash.
        """

        return Client.objects.create(
            name="Cliente de Teste",
            email=email,
            password_hash=make_password(password),
            status=status,
        )

    def test_login_accepts_correct_credentials(self, api_client):
        account = self.create_client("cliente.login@example.com")

        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/login/",
            {
                "role": "client",
                "email": "cliente.login@example.com",
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        assert response.data["user"]["id"] == account.pk

        # Consulta novamente a sessão para verificar sua persistência.
        me_response = api_client.get("/api/auth/me/")

        assert me_response.status_code == 200
        assert me_response.data["user"]["email"] == account.email

    def test_login_rejects_incorrect_password(self, api_client):
        self.create_client("cliente.senha.incorreta@example.com")

        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/login/",
            {
                "role": "client",
                "email": "cliente.senha.incorreta@example.com",
                "password": "SenhaErrada123",
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 401
        assert response.data["detail"] == "E-mail ou senha incorretos."

    def test_login_rejects_inactive_account(self, api_client):
        self.create_client(
            "cliente.inativo@example.com",
            status=AccountStatus.INACTIVE,
        )

        csrf = get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/login/",
            {
                "role": "client",
                "email": "cliente.inativo@example.com",
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 403

    def test_login_rejects_missing_csrf_token(self, api_client):
        get_csrf_token(api_client)

        response = api_client.post(
            "/api/auth/login/",
            {
                "role": "client",
                "email": "cliente.csrf@example.com",
                "password": PASSWORD,
            },
            format="json",
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_ends_authenticated_session(self, api_client):
        account = Client.objects.create(
            name="Cliente Logout",
            email="cliente.logout@example.com",
            password_hash=make_password(PASSWORD),
            status=AccountStatus.ACTIVE,
        )

        csrf = get_csrf_token(api_client)

        # Primeiro autentica a conta.
        login_response = api_client.post(
            "/api/auth/login/",
            {
                "role": "client",
                "email": account.email,
                "password": PASSWORD,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert login_response.status_code == 200

        # O login rotaciona o token CSRF: usa o novo cookie.
        csrf = api_client.cookies["csrftoken"].value

        # Encerra a sessão autenticada.
        logout_response = api_client.post(
            "/api/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert logout_response.status_code == 204

        # Depois do logout, a sessão não deve mais autenticar.
        me_response = api_client.get("/api/auth/me/")

        assert me_response.status_code == 401
