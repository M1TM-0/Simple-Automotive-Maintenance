import re

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import (
    validate_password as django_validate_password,
)
from django.core.exceptions import ValidationError


def validate_password(password: str) -> None:
    """Valida a senha: >=8, com letras e números, e não comum."""
    if len(password) < 8:
        raise ValidationError("A senha deve ter pelo menos 8 caracteres.")
    if not re.search(r"[a-zA-Z]", password) or not re.search(r"\d", password):
        raise ValidationError("Use letras e números.")
    try:
        django_validate_password(password)
    except ValidationError as exc:
        msgs = []
        for msg in exc.messages:
            low = msg.lower()
            if "common" in low or "comum" in low:
                msgs.append("Esta senha é muito comum.")
            else:
                msgs.append(msg)
        raise ValidationError(msgs) from None


def hash_password(password: str) -> str:
    validate_password(password)
    return make_password(password)


def verify_password(password: str, account) -> bool:
    """Verifica e atualiza o hash de forma transparente quando necessário."""

    def setter(raw_password: str) -> None:
        new_hash = make_password(raw_password)
        account.__class__.objects.filter(pk=account.pk).update(password_hash=new_hash)
        account.password_hash = new_hash

    return check_password(password, account.password_hash, setter=setter)
