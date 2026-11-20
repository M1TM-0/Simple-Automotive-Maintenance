"""Notificações: criação após o commit (BE-070) e leitura pelo destinatário (BE-069).

Regras (DP-11):

- **Só depois do commit.** `notify()` agenda a gravação com `transaction.on_commit`:
  uma operação que falha e é revertida não deixa notificação (o `@transactional`
  descarta os callbacks da tentativa desfeita, inclusive nas repetições).
- **Falha de notificação não derruba a operação.** O commit já aconteceu; o erro
  vai para o log `sam.notifications` e a resposta segue normal.
- **Destino seguro.** `url` só aceita página `.html` do projeto (mesma regra do
  CHECK `ck_notification_url` e do `auth.js`); fora disso a notificação vai sem link.
- **Chat agrupado.** Uma notificação não lida por conversa e destinatário: novas
  mensagens atualizam a mesma linha (texto, contagem e data) até ela ser lida.
"""

import logging
import re
from functools import partial

from apps.core.db import ClockTimestamp
from apps.notifications.models import Notification
from django.db import transaction

logger = logging.getLogger("sam.notifications")

SAFE_URL = re.compile(r"^[a-z-]+\.html(\?[A-Za-z0-9_=&.-]*)?$")
TITLE_MAX = 255
ROLES = ("client", "workshop")


def owner_filter(role: str, account_id: int) -> dict:
    if role not in ROLES:
        raise ValueError(f"Perfil sem notificações: {role!r}")
    return (
        {"client_id": account_id} if role == "client" else {"workshop_id": account_id}
    )


def for_recipient(role: str, account_id: int):
    return Notification.objects.filter(**owner_filter(role, account_id))


def safe_url(url: str | None) -> str | None:
    return url if url and SAFE_URL.fullmatch(url) else None


def chat_url(chat_id: int) -> str:
    return f"chat.html?id={chat_id}"


# ------------------------------------------------------------------ criação


def _run_safely(action, *args, **kwargs):
    try:
        action(*args, **kwargs)
    except Exception:  # noqa: BLE001 — já houve commit: registra e segue
        logger.exception(
            "notification_failed",
            extra={"action": getattr(action, "__name__", str(action))},
        )


def _create(role, account_id, title, message, url):
    Notification.objects.create(
        **owner_filter(role, account_id),
        title=title[:TITLE_MAX],
        message=message,
        url=safe_url(url),
    )


def notify(
    role: str, account_id: int, title: str, message: str, url: str | None = None
) -> None:
    """Agenda uma notificação para `role`/`account_id` depois do commit da transação."""
    owner_filter(role, account_id)  # perfil inválido é erro de programação: falha já
    transaction.on_commit(
        partial(_run_safely, _create, role, account_id, title, message, url)
    )


def _upsert_chat(chat_id, role, account_id, sender_name, preview):
    from apps.chat.models import Chat, MessageStatus
    from apps.chat.selectors import counterpart_messages

    url = chat_url(chat_id)
    with transaction.atomic():
        # Trava a conversa: duas mensagens confirmadas juntas não criam duas notificações.
        if not Chat.objects.select_for_update().filter(pk=chat_id).exists():
            return
        unread = (
            counterpart_messages(role)
            .filter(chat_id=chat_id)
            .exclude(status_message=MessageStatus.READ)
            .count()
        )
        if unread == 0:  # o destinatário já leu a conversa
            return
        title = (
            f"Nova mensagem de {sender_name}"
            if unread == 1
            else f"{unread} novas mensagens de {sender_name}"
        )
        pending = (
            for_recipient(role, account_id)
            .select_for_update()
            .filter(url=url, read_status=False)
            .order_by("-date_creation", "-id_notification")
            .first()
        )
        if pending is None:
            Notification.objects.create(
                **owner_filter(role, account_id),
                title=title[:TITLE_MAX],
                message=preview,
                url=url,
            )
            return
        pending.title = title[:TITLE_MAX]
        pending.message = preview
        pending.date_creation = ClockTimestamp()
        pending.save(update_fields=["title", "message", "date_creation"])


def notify_chat_message(
    chat_id: int, role: str, account_id: int, sender_name: str, preview: str
) -> None:
    """Nova mensagem para `role`/`account_id`: cria ou atualiza a notificação da conversa."""
    owner_filter(role, account_id)
    transaction.on_commit(
        partial(
            _run_safely, _upsert_chat, chat_id, role, account_id, sender_name, preview
        )
    )


# ------------------------------------------------------------------- leitura


def mark_read(role: str, account_id: int, notification_id: int) -> bool:
    """Marca uma notificação do próprio usuário. `False` = não existe para ele (404)."""
    queryset = for_recipient(role, account_id).filter(pk=notification_id)
    if not queryset.exists():
        return False
    queryset.filter(read_status=False).update(read_status=True)
    return True


def mark_all_read(role: str, account_id: int) -> int:
    return (
        for_recipient(role, account_id)
        .filter(read_status=False)
        .update(read_status=True)
    )


def mark_chat_read(role: str, account_id: int, chat_id: int) -> int:
    """Ler a conversa também apaga o aviso dela no sino."""
    return (
        for_recipient(role, account_id)
        .filter(url=chat_url(chat_id), read_status=False)
        .update(read_status=True)
    )
