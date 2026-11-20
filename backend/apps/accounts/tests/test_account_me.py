"""BE-031: `PATCH /me/` e `POST /me/password/` (cliente e oficina)."""

import io

import pytest
from apps.accounts.models import Client, Workshop
from apps.core.tests.factories import (
    ClientFactory,
    PagWorkshopFactory,
    WorkshopServiceFactory,
)
from apps.workshops.models import PagWorkshop
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

PASSWORD = "SenhaTeste123"
NEW_PASSWORD = "NovaSenha456"


def jpeg(name="perfil.jpg"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 200)).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def stored_name(url):
    """`http://testserver/media/profiles/x.jpg` → `profiles/x.jpg`."""
    return url.split("/media/", 1)[1]


@pytest.fixture
def client_account(db):
    return ClientFactory(
        password_hash=make_password(PASSWORD), phone_number="86 99999-0000"
    )


@pytest.fixture
def workshop_account(db):
    workshop = PagWorkshopFactory(
        workshop__password_hash=make_password(PASSWORD)
    ).workshop
    WorkshopServiceFactory(workshop=workshop)
    return workshop


# ------------------------------------------------------------- PATCH /me/


@pytest.mark.django_db
class TestClientProfile:
    def test_updates_name_and_phone(self, client_session, client_account):
        response = client_session.patch(
            "/api/me/",
            {"name": "  Ana Souza ", "phone_number": "86 98888-1111"},
            format="json",
        )

        assert response.status_code == 200
        user = response.json()["user"]
        assert (user["name"], user["phone_number"]) == ("Ana Souza", "86 98888-1111")
        client_account.refresh_from_db()
        assert client_account.name == "Ana Souza"

    def test_blank_phone_is_stored_as_null(self, client_session, client_account):
        response = client_session.patch("/api/me/", {"phone_number": ""}, format="json")

        assert response.status_code == 200
        client_account.refresh_from_db()
        assert client_account.phone_number is None

    def test_immutable_fields_in_body_are_ignored(self, client_session, client_account):
        original_hash = client_account.password_hash
        response = client_session.patch(
            "/api/me/",
            {
                "name": "Novo Nome",
                "email": "outro@example.com",
                "status": "blocked",
                "password_hash": "x",
                "name_fantasy": "não se aplica ao cliente",
            },
            format="json",
        )

        assert response.status_code == 200
        client_account.refresh_from_db()
        assert client_account.email != "outro@example.com"
        assert client_account.status == "active"
        assert client_account.password_hash == original_hash
        assert response.json()["user"]["email"] == client_account.email

    def test_blank_name_is_400_on_the_field(self, client_session):
        response = client_session.patch("/api/me/", {"name": ""}, format="json")

        assert response.status_code == 400
        assert "name" in response.json()

    def test_multipart_photo_upload(self, client_session, client_account):
        response = client_session.patch(
            "/api/me/", {"name": "Ana", "photo_profile": jpeg()}, format="multipart"
        )

        assert response.status_code == 200, response.json()
        url = response.json()["user"]["photo_profile"]
        assert "/media/profiles/clients/" in url
        client_account.refresh_from_db()
        assert client_account.photo_profile == stored_name(url)
        assert default_storage.exists(client_account.photo_profile)

    def test_replacing_photo_deletes_old_file_only_after_commit(
        self, client_session, client_account, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            first = client_session.patch(
                "/api/me/", {"photo_profile": jpeg()}, format="multipart"
            )
        old = stored_name(first.json()["user"]["photo_profile"])

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            second = client_session.patch(
                "/api/me/", {"photo_profile": jpeg()}, format="multipart"
            )
            # Antes do commit o arquivo antigo continua lá.
            assert default_storage.exists(old)

        assert second.status_code == 200
        for callback in callbacks:
            callback()
        assert not default_storage.exists(old)
        assert default_storage.exists(
            stored_name(second.json()["user"]["photo_profile"])
        )

    def test_empty_photo_removes_it(
        self, client_session, client_account, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            first = client_session.patch(
                "/api/me/", {"photo_profile": jpeg()}, format="multipart"
            )
        old = stored_name(first.json()["user"]["photo_profile"])

        with django_capture_on_commit_callbacks(execute=True):
            response = client_session.patch(
                "/api/me/", {"name": "Ana", "photo_profile": ""}, format="multipart"
            )

        assert response.status_code == 200
        assert response.json()["user"]["photo_profile"] is None
        client_account.refresh_from_db()
        assert client_account.photo_profile is None
        assert not default_storage.exists(old)

    def test_invalid_image_is_400_and_nothing_changes(
        self, client_session, client_account
    ):
        fake = SimpleUploadedFile(
            "perfil.jpg", b"<html>nao sou imagem</html>", content_type="image/jpeg"
        )

        response = client_session.patch(
            "/api/me/", {"name": "Outro", "photo_profile": fake}, format="multipart"
        )

        assert response.status_code == 400
        assert "photo_profile" in response.json()
        client_account.refresh_from_db()
        assert client_account.name != "Outro"
        assert client_account.photo_profile is None

    def test_photo_as_json_string_is_400(self, client_session):
        response = client_session.patch(
            "/api/me/", {"photo_profile": "https://evil.example/x.png"}, format="json"
        )

        assert response.status_code == 400
        assert response.json() == {"photo_profile": ["Envie um arquivo de imagem."]}


@pytest.mark.django_db
class TestWorkshopProfile:
    def test_updates_names_and_phone_but_not_cnpj(
        self, workshop_session, workshop_account
    ):
        cnpj = workshop_account.cnpj
        response = workshop_session.patch(
            "/api/me/",
            {
                "name_fantasy": "Auto Center Novo",
                "name_responsible": "João",
                "phone_number": "86 3222-0000",
                "cnpj": "00000000000000",
                "email": "x@example.com",
            },
            format="json",
        )

        assert response.status_code == 200
        user = response.json()["user"]
        assert (user["name"], user["name_responsible"], user["setup_complete"]) == (
            "Auto Center Novo",
            "João",
            True,
        )
        workshop_account.refresh_from_db()
        assert workshop_account.cnpj == cnpj
        assert workshop_account.email != "x@example.com"

    def test_name_is_an_alias_of_name_fantasy(self, workshop_session, workshop_account):
        response = workshop_session.patch(
            "/api/me/", {"name": "Oficina do Zé"}, format="json"
        )

        assert response.status_code == 200
        workshop_account.refresh_from_db()
        assert workshop_account.name_fantasy == "Oficina do Zé"

    def test_photo_goes_to_the_page_and_removal_restores_default(
        self, workshop_session, workshop_account, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = workshop_session.patch(
                "/api/me/", {"photo_profile": jpeg()}, format="multipart"
            )
        assert response.status_code == 200
        url = response.json()["user"]["photo_profile"]
        assert "/media/profiles/workshops/" in url
        page = PagWorkshop.objects.get(workshop=workshop_account)
        assert page.photo_profile == stored_name(url)

        with django_capture_on_commit_callbacks(execute=True):
            response = workshop_session.patch(
                "/api/me/", {"photo_profile": ""}, format="multipart"
            )

        page.refresh_from_db()
        assert page.photo_profile == "default-profile.png"
        assert response.json()["user"]["photo_profile"].endswith(
            "/static/core/default-profile.png"
        )
        assert not default_storage.exists(stored_name(url))


# ------------------------------------------------------ POST /me/password/


def change_password(api, current=PASSWORD, new=NEW_PASSWORD):
    return api.post(
        "/api/me/password/",
        {"current_password": current, "new_password": new},
        format="json",
    )


@pytest.mark.django_db
class TestChangePassword:
    def test_wrong_current_password_is_400_on_the_field(self, client_session):
        response = change_password(client_session, current="SenhaErrada000")

        assert response.status_code == 400
        assert response.json() == {"current_password": ["Senha atual incorreta."]}

    def test_weak_new_password_is_400_on_the_field(self, client_session):
        response = change_password(client_session, new="12345678")

        assert response.status_code == 400
        assert response.json() == {"new_password": ["Use letras e números."]}

    @pytest.mark.parametrize("role", ["client", "workshop"])
    def test_success_invalidates_other_sessions_but_keeps_current(
        self, role, account_session, client_account, workshop_account
    ):
        account = client_account if role == "client" else workshop_account
        current = account_session(account, role)
        other = account_session(account, role)
        assert other.get("/api/auth/me/").status_code == 200

        response = change_password(current)

        assert response.status_code == 204
        assert current.get("/api/auth/me/").status_code == 200
        assert other.get("/api/auth/me/").status_code == 401

        model = Client if role == "client" else Workshop
        stored = model.objects.get(pk=account.pk).password_hash
        assert check_password(NEW_PASSWORD, stored)
        assert not check_password(PASSWORD, stored)

    def test_new_password_works_for_login(self, client_session, client_account):
        assert change_password(client_session).status_code == 204

        api = APIClient()
        old = api.post(
            "/api/auth/login/",
            {"role": "client", "email": client_account.email, "password": PASSWORD},
            format="json",
        )
        new = api.post(
            "/api/auth/login/",
            {"role": "client", "email": client_account.email, "password": NEW_PASSWORD},
            format="json",
        )
        assert (old.status_code, new.status_code) == (401, 200)

    def test_current_session_key_is_rotated(self, client_session):
        before = client_session.cookies["sessionid"].value

        change_password(client_session)

        assert client_session.cookies["sessionid"].value != before
