import pytest
from apps.accounts.models import Client
from apps.accounts.passwords import verify_password
from django.contrib.auth.hashers import (
    check_password,
    identify_hasher,
    make_password,
)


@pytest.mark.django_db
class TestPasswordRehashIntegration:
    def test_upgrades_pbkdf2_hash_and_persists_argon2(self):
        password = "VentoAzul482"

        old_hash = make_password(
            password,
            hasher="pbkdf2_sha256",
        )

        account = Client.objects.create(
            name="Cliente Teste",
            email="cliente.teste.integracao@example.com",
            password_hash=old_hash,
        )

        assert identify_hasher(account.password_hash).algorithm == "pbkdf2_sha256"

        result = verify_password(password, account)

        assert result is True

        # Busca novamente no PostgreSQL para verificar a persistência.
        reloaded_account = Client.objects.get(pk=account.pk)

        assert identify_hasher(reloaded_account.password_hash).algorithm == "argon2"
        assert check_password(password, reloaded_account.password_hash) is True

    def test_incorrect_password_does_not_upgrade_hash(self):
        password = "VentoAzul482"

        old_hash = make_password(
            password,
            hasher="pbkdf2_sha256",
        )

        account = Client.objects.create(
            name="Cliente Teste",
            email="cliente.teste.incorreto@example.com",
            password_hash=old_hash,
        )

        result = verify_password("SenhaErrada123", account)

        assert result is False

        reloaded_account = Client.objects.get(pk=account.pk)

        assert reloaded_account.password_hash == old_hash
        assert (
            identify_hasher(reloaded_account.password_hash).algorithm == "pbkdf2_sha256"
        )
