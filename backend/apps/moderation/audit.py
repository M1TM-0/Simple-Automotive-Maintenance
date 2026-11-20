"""Log de auditoria das ações de administração (BE-035).

Registra no logger `sam.audit` (JSON estruturado, BE-018): login/logout/falha de
login de usuários `is_staff` no Django Admin e toda ação de escrita nas rotas
`/api/admin/*`. As ações feitas pelas telas do Django Admin ficam também no
`LogEntry` do próprio Django.
"""

import logging

from apps.core.logging import mask_email
from apps.core.throttles import client_ip
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

audit_logger = logging.getLogger("sam.audit")


def _admin_fields(user):
    return {
        "admin_id": getattr(user, "pk", None),
        "admin_username": getattr(user, "get_username", lambda: None)(),
    }


def _ip(request):
    # Atrás do Nginx, REMOTE_ADDR é o proxy: mesma regra dos limites de taxa (NUM_PROXIES).
    return client_ip(request) if request is not None else None


def log_admin_action(request, action, *, target_type=None, target_id=None, **extra):
    """Registra uma ação de administrador (quem, o quê, sobre qual alvo, resultado)."""
    audit_logger.info(
        "admin.%s",
        action,
        extra={
            "event": f"admin.{action}",
            **_admin_fields(request.user),
            "ip": _ip(request),
            "method": request.method,
            "path": request.path,
            "target_type": target_type,
            "target_id": target_id,
            **extra,
        },
    )


@receiver(user_logged_in, dispatch_uid="sam.audit.admin_login")
def _on_admin_login(sender, request, user, **kwargs):
    if user.is_staff:
        audit_logger.info(
            "admin.login",
            extra={"event": "admin.login", **_admin_fields(user), "ip": _ip(request)},
        )


@receiver(user_logged_out, dispatch_uid="sam.audit.admin_logout")
def _on_admin_logout(sender, request, user, **kwargs):
    if user is not None and user.is_staff:
        audit_logger.info(
            "admin.logout",
            extra={"event": "admin.logout", **_admin_fields(user), "ip": _ip(request)},
        )


@receiver(user_login_failed, dispatch_uid="sam.audit.admin_login_failed")
def _on_admin_login_failed(sender, credentials, request=None, **kwargs):
    username = credentials.get("username") or ""
    audit_logger.warning(
        "admin.login_failed",
        extra={
            "event": "admin.login_failed",
            "admin_username": mask_email(username) if "@" in username else username,
            "ip": _ip(request),
        },
    )
