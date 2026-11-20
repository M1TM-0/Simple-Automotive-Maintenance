"""Token assinado de redefinição de senha, sem tabela (BE-032, DP-12).

O token embute o perfil, o id da conta e o fingerprint do hash atual da senha.
Quando a senha muda o fingerprint deixa de conferir: o token vira de uso único.
"""

from apps.accounts.sessions import fingerprint_matches, password_fingerprint
from django.core import signing

SALT = "sam.password-reset"
MAX_AGE = 60 * 60  # 1 hora


class InvalidResetToken(Exception):
    pass


class ExpiredResetToken(InvalidResetToken):
    pass


def make_password_reset_token(role: str, account) -> str:
    payload = {"r": role, "i": int(account.pk), "f": password_fingerprint(account)}
    return signing.dumps(payload, salt=SALT)


def load_password_reset_token(token: str):
    """Devolve (role, id, fingerprint). Levanta ExpiredResetToken/InvalidResetToken."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired:
        raise ExpiredResetToken from None
    except signing.BadSignature:
        raise InvalidResetToken from None
    if not isinstance(data, dict):
        raise InvalidResetToken
    return data.get("r"), data.get("i"), data.get("f")


def token_matches_account(account, fingerprint) -> bool:
    return fingerprint_matches(account, fingerprint)
