"""Casos de uso de contas: cadastro, login, perfil e senhas (BE-024…BE-033); situação da
conta, desativação e anonimização pela administração (BE-075, BE-078)."""

import logging
import threading

from apps.accounts.emails import send_password_reset_email
from apps.accounts.models import AccountStatus, Client, Workshop
from apps.accounts.passwords import hash_password, verify_password
from apps.accounts.tokens import (
    ExpiredResetToken,
    InvalidResetToken,
    load_password_reset_token,
    make_password_reset_token,
    token_matches_account,
)
from apps.core.exceptions import ApiConflict, ApiThrottled, ApiValidationFailure
from apps.core.fields import media_url
from apps.core.logging import log_auth_event
from apps.core.storage import apply_image_changes, delete_stored_image
from apps.core.throttles import login_lockouts
from apps.core.transactions import transactional
from apps.workshops.domain import is_setup_complete
from apps.workshops.models import PagWorkshop
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models.functions import Lower
from rest_framework.exceptions import PermissionDenied, ValidationError

logger = logging.getLogger("sam.auth")

ACCOUNT_MODELS = {"client": Client, "workshop": Workshop}

BLOCKED_MESSAGES = {
    AccountStatus.BLOCKED: "Conta bloqueada. Entre em contato com o suporte.",
    AccountStatus.INACTIVE: "Conta desativada. Entre em contato com o suporte.",
}
LOCKOUT_MESSAGE = "Muitas tentativas de login sem sucesso."
RESET_INVALID = "Este link de redefinição é inválido ou já foi usado. Peça um novo."
RESET_EXPIRED = "Este link de redefinição expirou. Peça um novo."

# Hash fictício: e-mail inexistente custa o mesmo que senha errada (não enumeração).
_DUMMY_HASH = make_password("dummy-password-for-timing")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_account_model(role: str):
    model = ACCOUNT_MODELS.get(role)
    if model is None:
        raise ValidationError({"role": ["Perfil inválido."]})
    return model


def find_account(role: str, email: str):
    """Conta do perfil com o e-mail informado (sem diferenciar maiúsculas) ou None."""
    return (
        get_account_model(role)
        .objects.annotate(normalized_email=Lower("email"))
        .filter(normalized_email=normalize_email(email))
        .first()
    )


def get_account_name(account, role: str) -> str:
    return account.name if role == "client" else account.name_fantasy


def public_account(account, role: str, request=None) -> dict:
    """Forma `{user}` devolvida por cadastro, login, `/auth/me/` e `PATCH /me/`."""
    if role == "client":
        photo = account.photo_profile
    else:
        photo = (
            PagWorkshop.objects.filter(workshop_id=account.pk)
            .values_list("photo_profile", flat=True)
            .first()
        )

    data = {
        "id": account.pk,
        "role": role,
        "name": get_account_name(account, role),
        "email": account.email,
        "phone_number": account.phone_number,
        "photo_profile": media_url(photo, request),
        "status": account.status,
        "setup_complete": is_setup_complete(account) if role == "workshop" else None,
    }
    if role == "workshop":
        data["name_fantasy"] = account.name_fantasy
        data["name_responsible"] = account.name_responsible
    return data


# --------------------------------------------------------------------- cadastro


@transactional
def register_account(data: dict, *, ip=None):
    """Cria Cliente ou Oficina (+ PAG_WORKSHOP na mesma transação) — BE-026.

    Duplicidades são detectadas pelos índices do banco (`uq_*_email`,
    `workshop_cnpj_key`) e traduzidas para 409 com o campo (`email`/`cnpj`).
    """
    role = data["role"]
    email = normalize_email(data["email"])

    # Atalho para a mensagem por campo sem gastar um hash; o índice único
    # continua sendo a garantia contra corrida (tratado em db_errors).
    if find_account(role, email) is not None:
        raise ApiConflict({"email": ["Este e-mail já está em uso."]})

    common = {
        "email": email,
        "password_hash": hash_password(data["password"]),
        "phone_number": (data.get("phone_number") or "").strip() or None,
        "status": AccountStatus.ACTIVE,
    }

    if role == "client":
        account = Client.objects.create(name=data["name"].strip(), **common)
    else:
        account = Workshop.objects.create(
            name_fantasy=data["name_fantasy"].strip(),
            name_responsible=data["name_responsible"].strip(),
            cnpj=data["cnpj"],
            **common,
        )
        PagWorkshop.objects.create(workshop=account)

    log_auth_event("register", role=role, email=email, ip=ip, success=True)
    return account, role


# ------------------------------------------------------------------------ login


def authenticate_account(role: str, email: str, password: str, *, ip=None):
    """Autentica por perfil + e-mail + senha — BE-027 e BE-033.

    Devolve (account, role) ou None (mensagem única para e-mail inexistente e
    senha errada). Conta não ativa com senha correta → 403. Falhas repetidas
    bloqueiam o par IP+conta (e a conta, num limiar maior) → 429.
    """
    model = get_account_model(role)
    email_norm = normalize_email(email)
    ip_ident = f"{ip}:{role}:{email_norm}"
    account_ident = f"{role}:{email_norm}"
    lockouts = login_lockouts()
    by_ip, by_account = lockouts

    wait = max(by_ip.retry_after(ip_ident), by_account.retry_after(account_ident))
    if wait:
        log_auth_event(
            "login", role=role, email=email_norm, ip=ip, success=False, reason="locked"
        )
        raise ApiThrottled(wait=wait, detail=LOCKOUT_MESSAGE)

    account = (
        model.objects.annotate(normalized_email=Lower("email"))
        .filter(normalized_email=email_norm)
        .first()
    )

    if account is None:
        check_password(password, _DUMMY_HASH)
        reason = "not_found"
    elif not verify_password(password, account):
        reason = "bad_password"
    else:
        reason = None

    if reason is not None:
        log_auth_event(
            "login", role=role, email=email_norm, ip=ip, success=False, reason=reason
        )
        locks = (
            by_ip.register_failure(ip_ident),
            by_account.register_failure(account_ident),
        )
        if any(locks):
            log_auth_event(
                "lockout",
                role=role,
                email=email_norm,
                ip=ip,
                success=False,
                lock_seconds=max(locks),
            )
        return None

    if account.status != AccountStatus.ACTIVE:
        log_auth_event(
            "login",
            role=role,
            email=email_norm,
            ip=ip,
            success=False,
            reason=account.status,
        )
        raise PermissionDenied(
            BLOCKED_MESSAGES.get(
                account.status, BLOCKED_MESSAGES[AccountStatus.BLOCKED]
            )
        )

    by_ip.reset(ip_ident)
    by_account.reset(account_ident)
    log_auth_event("login", role=role, email=email_norm, ip=ip, success=True)
    return account, role


# ----------------------------------------------------------------------- perfil


def _lock_account(principal):
    return (
        get_account_model(principal.role)
        .objects.select_for_update()
        .get(pk=principal.id)
    )


@transactional
def update_account_profile(principal, data: dict):
    """`PATCH /me/` — BE-031. E-mail, CNPJ e status nunca chegam aqui (serializer).

    Foto: `ProcessedImage` substitui, `None` remove; o arquivo antigo só é
    apagado depois do commit (`apply_image_changes`).
    """
    role = principal.role
    account = _lock_account(principal)
    fields = []

    if role == "client":
        if "name" in data:
            account.name = data["name"]
            fields.append("name")
    else:
        name_fantasy = data.get("name_fantasy", data.get("name"))
        if name_fantasy is not None:
            account.name_fantasy = name_fantasy
            fields.append("name_fantasy")
        if "name_responsible" in data:
            account.name_responsible = data["name_responsible"]
            fields.append("name_responsible")

    if "phone_number" in data:
        account.phone_number = data["phone_number"] or None
        fields.append("phone_number")

    if fields:
        account.save(update_fields=fields)

    if "photo_profile" in data:
        photo = data["photo_profile"]
        if role == "client":
            apply_image_changes(
                account, {"photo_profile": photo}, folder="profiles/clients"
            )
        else:
            page, _ = PagWorkshop.objects.get_or_create(workshop=account)
            apply_image_changes(
                page, {"photo_profile": photo}, folder="profiles/workshops"
            )
            if photo is None:
                # Sem foto a página volta ao padrão do banco (DEFAULT 'default-profile.png').
                PagWorkshop.objects.filter(pk=page.pk).update(
                    photo_profile=settings.SAM_DEFAULT_PROFILE_IMAGE
                )

    return account


# ----------------------------------------------------------------------- senhas


@transactional
def change_account_password(principal, current_password: str, new_password: str):
    """`POST /me/password/` — BE-031. O novo hash invalida as outras sessões."""
    account = _lock_account(principal)
    if not verify_password(current_password, account):
        raise ValidationError({"current_password": ["Senha atual incorreta."]})
    account.password_hash = hash_password(new_password)
    account.save(update_fields=["password_hash"])
    return account


def _send_reset_email(to_email, token, role) -> bool:
    try:
        send_password_reset_email(to_email=to_email, token=token, role=role)
    except Exception:
        # A resposta continua genérica; a falha fica registrada para a operação.
        logger.exception(
            "auth.password_reset_email_failed",
            extra={"event": "password_reset_email_failed", "role": role},
        )
        return False
    return True


def request_password_reset(*, email: str, role=None, ip=None) -> None:
    """`POST /auth/password-reset/` — BE-032. Nunca revela se o e-mail existe."""
    email_norm = normalize_email(email)
    roles = (role,) if role in ACCOUNT_MODELS else tuple(ACCOUNT_MODELS)
    sent = False

    for current_role in roles:
        account = find_account(current_role, email_norm)
        if account is None or account.status != AccountStatus.ACTIVE:
            continue
        token = make_password_reset_token(current_role, account)
        if settings.SAM_EMAIL_ASYNC:
            # O tempo de resposta não pode denunciar que o e-mail existe (o envio SMTP
            # leva centenas de ms): o e-mail sai numa thread e a falha fica no log.
            threading.Thread(
                target=_send_reset_email,
                args=(account.email, token, current_role),
                name="sam-password-reset-email",
                daemon=True,
            ).start()
            sent = True
        else:
            sent = _send_reset_email(account.email, token, current_role) or sent

    log_auth_event(
        "password_reset_request",
        role=role or "any",
        email=email_norm,
        ip=ip,
        success=sent,
    )


@transactional
def confirm_password_reset(*, token: str, new_password: str):
    """`POST /auth/password-reset/confirm/` — BE-032. Token de uso único e prazo de 1 h."""
    try:
        role, account_id, fingerprint = load_password_reset_token(token)
    except ExpiredResetToken:
        raise ApiValidationFailure(RESET_EXPIRED) from None
    except InvalidResetToken:
        raise ApiValidationFailure(RESET_INVALID) from None

    model = ACCOUNT_MODELS.get(role)
    if model is None or not isinstance(account_id, int):
        raise ApiValidationFailure(RESET_INVALID)

    # FOR UPDATE: duas confirmações simultâneas do mesmo token não passam ambas.
    account = model.objects.select_for_update().filter(pk=account_id).first()
    if (
        account is None
        or account.status != AccountStatus.ACTIVE
        or not token_matches_account(account, fingerprint)
    ):
        raise ApiValidationFailure(RESET_INVALID)

    account.password_hash = hash_password(new_password)
    account.save(update_fields=["password_hash"])
    log_auth_event(
        "password_reset", role=role, email=account.email, ip=None, success=True
    )
    return account, role


# -------------------------------------------------------------------- favoritos


@transactional
def add_favorite(client_id: int, workshop_id: int):
    """Favorita uma oficina ativa (BE-062). Idempotente: devolve (favorito, criado?)."""
    from apps.accounts.models import Favorite
    from django.db import IntegrityError, transaction
    from rest_framework.exceptions import NotFound

    if not Workshop.objects.filter(
        pk=workshop_id, status=AccountStatus.ACTIVE
    ).exists():
        raise NotFound("Oficina não encontrada.")

    existing = Favorite.objects.filter(
        client_id=client_id, workshop_id=workshop_id
    ).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            return Favorite.objects.create(
                client_id=client_id, workshop_id=workshop_id
            ), True
    except IntegrityError:
        # Corrida com outro POST igual: `unique_favorite` garante um só registro.
        return Favorite.objects.get(client_id=client_id, workshop_id=workshop_id), False


@transactional
def remove_favorite(client_id: int, workshop_id: int) -> None:
    from apps.accounts.models import Favorite
    from rest_framework.exceptions import NotFound

    deleted, _ = Favorite.objects.filter(
        client_id=client_id, workshop_id=workshop_id
    ).delete()
    if not deleted:
        raise NotFound("Esta oficina não está nos seus favoritos.")


# ------------------------------------------- situação da conta (BE-075, BE-078)

# DP-18 / ADR 0018. A conta nunca é apagada (RESTRICT preserva atendimentos,
# orçamentos, avaliações e denúncias): é desativada e, a pedido do titular,
# anonimizada. `blocked`/`inactive` já derrubam as sessões abertas (a
# autenticação confere o status a cada requisição), recusam o login com 403 e
# tiram a oficina das leituras públicas (`public_workshops`, DP-20).
ANONYMIZED_NAME = "Anônimo"
ANONYMIZED_EMAIL_DOMAIN = (
    "anonimizado.invalid"  # TLD reservado (RFC 2606): nunca entrega
)


def anonymized_email(role: str, account_id: int) -> str:
    return f"anonimo-{role}-{account_id}@{ANONYMIZED_EMAIL_DOMAIN}"


def is_anonymized(account) -> bool:
    return account.email.endswith("@" + ANONYMIZED_EMAIL_DOMAIN)


@transactional
def set_account_status(role: str, account_id: int, status: str):
    """Bloqueia, desativa ou reativa. Devolve `(conta, status anterior)`.

    Conta anonimizada não volta a `active`: não há e-mail nem senha para entrar.
    """
    if status not in AccountStatus.values:
        raise ValueError(f"Status de conta inválido: {status!r}")
    account = get_account_model(role).objects.select_for_update().get(pk=account_id)
    previous = account.status
    if status == AccountStatus.ACTIVE and is_anonymized(account):
        raise ApiConflict("Uma conta anonimizada não pode ser reativada.")
    if previous != status:
        account.status = status
        account.save(update_fields=["status"])
    return account, previous


@transactional
def anonymize_account(role: str, account_id: int):
    """Apaga os dados pessoais sem quebrar as FKs (BE-078, ADR 0018). Irreversível.

    - Cliente: nome → "Anônimo"; e-mail → endereço `.invalid` único; telefone e
      foto removidos; favoritos e notificações (só dele) apagados.
    - Oficina: responsável → "Anônimo"; e-mail, telefone, senha e as fotos da
      página removidos; notificações apagadas. Nome fantasia e CNPJ ficam: são
      dados da empresa e identificam o prestador no histórico dos clientes.
    - Ambos: senha trocada por hash inutilizável (`make_password(None)`: nenhuma
      senha confere e as sessões caem) e status `inactive`.

    Atendimentos, orçamentos, histórico, mensagens e avaliações permanecem; o nome
    exibido nas avaliações vira "Anônimo". Os arquivos de foto são apagados do
    storage depois do commit. Repetir é inofensivo.
    """
    from apps.accounts.models import Favorite
    from apps.notifications.models import Notification

    account = get_account_model(role).objects.select_for_update().get(pk=account_id)
    old_files = []
    if role == "client":
        old_files.append(account.photo_profile)
        account.name = ANONYMIZED_NAME
        account.photo_profile = None
        fields = ["name", "photo_profile"]
        Favorite.objects.filter(client_id=account.pk).delete()
        Notification.objects.filter(client_id=account.pk).delete()
    else:
        account.name_responsible = ANONYMIZED_NAME
        fields = ["name_responsible"]
        page = (
            PagWorkshop.objects.select_for_update()
            .filter(workshop_id=account.pk)
            .first()
        )
        if page is not None:
            old_files += [page.photo_profile, page.photo_banner]
            page.photo_profile = settings.SAM_DEFAULT_PROFILE_IMAGE
            page.photo_banner = None
            page.save(update_fields=["photo_profile", "photo_banner"])
        Notification.objects.filter(workshop_id=account.pk).delete()

    account.email = anonymized_email(role, account.pk)
    account.phone_number = None
    account.password_hash = make_password(None)
    account.status = AccountStatus.INACTIVE
    account.save(
        update_fields=[*fields, "email", "phone_number", "password_hash", "status"]
    )
    transaction.on_commit(lambda: [delete_stored_image(name) for name in old_files])
    return account
