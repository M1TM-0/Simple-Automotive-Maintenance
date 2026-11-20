from unittest.mock import MagicMock

from apps.accounts.passwords import (
    hash_password,
    validate_password,
    verify_password,
)
from django.contrib.auth.hashers import (
    identify_hasher,
    make_password,
)
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase


class PasswordValidationTests(SimpleTestCase):
    def test_rejects_password_shorter_than_eight_characters(self):
        with self.assertRaises(ValidationError):
            validate_password("Ab1")

    def test_rejects_password_without_letters(self):
        with self.assertRaises(ValidationError):
            validate_password("12345678")

    def test_rejects_password_without_digits(self):
        with self.assertRaises(ValidationError):
            validate_password("SenhaTeste")

    def test_rejects_common_password(self):
        with self.assertRaises(ValidationError):
            validate_password("password1")

    def test_accepts_valid_password(self):
        validate_password("VentoAzul482")


class PasswordHashTests(SimpleTestCase):
    def test_generates_argon2_hash(self):
        encoded = hash_password("VentoAzul482")

        self.assertEqual(
            identify_hasher(encoded).algorithm,
            "argon2",
        )

    def test_verifies_correct_password(self):
        encoded = hash_password("VentoAzul482")

        account = MagicMock()
        account.password_hash = encoded

        self.assertTrue(verify_password("VentoAzul482", account))

    def test_rejects_incorrect_password(self):
        encoded = hash_password("VentoAzul482")

        account = MagicMock()
        account.password_hash = encoded

        self.assertFalse(verify_password("SenhaErrada123", account))


class PasswordRehashTests(SimpleTestCase):
    def test_upgrades_pbkdf2_hash_to_argon2(self):
        password = "VentoAzul482"

        old_hash = make_password(
            password,
            hasher="pbkdf2_sha256",
        )

        class FakeAccount:
            objects = MagicMock()

            def __init__(self):
                self.pk = 1
                self.password_hash = old_hash

        account = FakeAccount()

        result = verify_password(password, account)

        self.assertTrue(result)

        self.assertEqual(
            identify_hasher(account.password_hash).algorithm,
            "argon2",
        )

        FakeAccount.objects.filter.assert_called_once_with(pk=account.pk)

        FakeAccount.objects.filter.return_value.update.assert_called_once_with(
            password_hash=account.password_hash
        )

    def test_does_not_upgrade_hash_when_password_is_incorrect(self):
        password = "VentoAzul482"

        old_hash = make_password(
            password,
            hasher="pbkdf2_sha256",
        )

        class FakeAccount:
            def __init__(self):
                self.pk = 1
                self.password_hash = old_hash
                self.save = MagicMock()

        account = FakeAccount()

        result = verify_password("SenhaErrada123", account)

        self.assertFalse(result)
        self.assertEqual(account.password_hash, old_hash)

        account.save.assert_not_called()
