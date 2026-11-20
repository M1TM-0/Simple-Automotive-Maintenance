"""BE-024 / BE-026: cadastro — duplicidades por campo, senha fraca e transação."""

from unittest import mock

import pytest
from apps.accounts.models import Client, Workshop
from apps.accounts.services import register_account
from apps.core.tests.factories import ClientFactory, WorkshopFactory, make_cnpj
from apps.workshops.models import PagWorkshop
from django.contrib.auth.hashers import identify_hasher
from django.db import DatabaseError

PASSWORD = "SenhaTeste123"
URL = "/api/auth/register/"


def client_payload(**extra):
    return {
        "role": "client",
        "name": "Ana",
        "email": "ana@example.com",
        "password": PASSWORD,
        **extra,
    }


def workshop_payload(**extra):
    return {
        "role": "workshop",
        "name_fantasy": "Auto Center",
        "name_responsible": "João",
        "cnpj": make_cnpj(4242),
        "email": "oficina@example.com",
        "password": PASSWORD,
        **extra,
    }


@pytest.mark.django_db
class TestPasswordPolicy:
    def test_hash_has_algorithm_prefix_and_no_plain_text(self, api_client):
        response = api_client.post(
            URL, client_payload(password="abc12345x"), format="json"
        )

        assert response.status_code == 201
        stored = Client.objects.get(email="ana@example.com").password_hash
        assert "abc12345x" not in stored
        assert stored.startswith("argon2$")
        assert identify_hasher(stored).algorithm == "argon2"

    def test_digits_only_password_is_rejected(self, api_client):
        response = api_client.post(
            URL, client_payload(password="12345678"), format="json"
        )

        assert response.status_code == 400
        assert response.json() == {"password": ["Use letras e números."]}

    def test_short_password_is_rejected(self, api_client):
        response = api_client.post(URL, client_payload(password="ab1"), format="json")
        assert response.status_code == 400
        assert "password" in response.json()


@pytest.mark.django_db
class TestDuplicates:
    def test_same_email_same_role_is_409_on_email_case_insensitive(self, api_client):
        ClientFactory(email="ana@example.com")

        response = api_client.post(
            URL, client_payload(email="ANA@Example.com"), format="json"
        )

        assert response.status_code == 409
        assert response.json() == {"email": ["Este e-mail já está em uso."]}
        assert Client.objects.count() == 1

    def test_email_of_a_client_can_register_a_workshop(self, api_client):
        ClientFactory(email="oficina@example.com")
        response = api_client.post(URL, workshop_payload(), format="json")
        assert response.status_code == 201

    def test_duplicate_cnpj_is_409_on_cnpj(self, api_client):
        WorkshopFactory(cnpj=make_cnpj(4242))

        response = api_client.post(URL, workshop_payload(), format="json")

        assert response.status_code == 409
        assert response.json() == {"cnpj": ["Já existe uma oficina com este CNPJ."]}
        assert not Workshop.objects.filter(email="oficina@example.com").exists()

    def test_race_on_email_is_translated_by_the_unique_index(self, api_client):
        """Se a checagem prévia perder a corrida, o índice uq_client_email responde por campo."""
        ClientFactory(email="ana@example.com")

        with mock.patch("apps.accounts.services.find_account", return_value=None):
            response = api_client.post(URL, client_payload(), format="json")

        assert response.status_code == 409
        assert response.json() == {"email": ["Este e-mail já está em uso."]}


@pytest.mark.django_db
class TestValidation:
    def test_client_requires_name(self, api_client):
        response = api_client.post(URL, client_payload(name=""), format="json")
        assert response.status_code == 400
        assert response.json() == {"name": ["Este campo é obrigatório."]}

    def test_workshop_requires_company_fields(self, api_client):
        response = api_client.post(
            URL,
            workshop_payload(name_fantasy="", name_responsible="", cnpj=""),
            format="json",
        )
        assert response.status_code == 400
        assert set(response.json()) == {"name_fantasy", "name_responsible", "cnpj"}

    def test_invalid_cnpj_check_digit(self, api_client):
        cnpj = make_cnpj(4242)
        bad = cnpj[:-1] + str((int(cnpj[-1]) + 1) % 10)
        response = api_client.post(URL, workshop_payload(cnpj=bad), format="json")
        assert response.status_code == 400
        assert "cnpj" in response.json()


@pytest.mark.django_db
class TestTransaction:
    def test_page_failure_rolls_back_the_workshop(self):
        data = workshop_payload()
        with (
            mock.patch.object(
                PagWorkshop.objects, "create", side_effect=DatabaseError("falhou")
            ),
            pytest.raises(DatabaseError),
        ):
            register_account(data)

        assert not Workshop.objects.filter(email=data["email"]).exists()

    def test_workshop_and_page_are_created_together(self, api_client):
        response = api_client.post(URL, workshop_payload(), format="json")

        assert response.status_code == 201
        workshop = Workshop.objects.get(email="oficina@example.com")
        assert PagWorkshop.objects.filter(workshop=workshop).count() == 1
        assert response.json()["user"]["setup_complete"] is False
