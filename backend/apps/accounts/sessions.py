"""Sessão de domínio (cliente/oficina) sobre a sessão do Django (BE-025, DP-02).

A sessão guarda o perfil, o id da conta e um *fingerprint* do `password_hash`.
Quando a senha muda (troca, redefinição ou rehash), o fingerprint deixa de
conferir e todas as sessões abertas antes da mudança são recusadas (BE-031).
"""

from django.middleware.csrf import rotate_token
from django.utils.crypto import constant_time_compare, salted_hmac

SESSION_ROLE = "sam_account_role"
SESSION_ID = "sam_account_id"
SESSION_PASSWORD = "sam_account_pwd"

ACCOUNT_ROLES = ("client", "workshop")

_FINGERPRINT_SALT = "sam.accounts.password-fingerprint"


def password_fingerprint(account) -> str:
    """HMAC (com SECRET_KEY) do hash da senha: muda sempre que a senha muda."""
    return salted_hmac(
        _FINGERPRINT_SALT, account.password_hash or "", algorithm="sha256"
    ).hexdigest()


def fingerprint_matches(account, value) -> bool:
    return bool(value) and constant_time_compare(password_fingerprint(account), value)


def write_account_session(session, account, role) -> None:
    session[SESSION_ROLE] = role
    session[SESSION_ID] = account.pk
    session[SESSION_PASSWORD] = password_fingerprint(account)


def read_account_session(session):
    """Devolve (role, id, fingerprint) da sessão; valores ausentes viram None."""
    return (
        session.get(SESSION_ROLE),
        session.get(SESSION_ID),
        session.get(SESSION_PASSWORD),
    )


def start_account_session(request, account, role) -> None:
    """Abre a sessão após login/cadastro: nova chave, CSRF rotacionado e identidade gravada.

    `flush()` descarta qualquer identidade anterior (inclusive de admin Django)
    e emite uma chave nova, evitando fixação de sessão.
    """
    request.session.flush()
    write_account_session(request.session, account, role)
    rotate_token(request._request if hasattr(request, "_request") else request)


def refresh_account_session(request, account, role) -> None:
    """Mantém a sessão atual válida após a troca de senha (nova chave + novo fingerprint)."""
    request.session.cycle_key()
    write_account_session(request.session, account, role)
