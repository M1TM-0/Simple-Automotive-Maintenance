"""Casos de uso do chat (BE-057, BE-058).

Nova mensagem notifica o interlocutor (BE-070), uma notificação por conversa até
ser lida; ler a conversa marca essa notificação como lida.
"""

from apps.accounts.models import AccountStatus, Workshop
from apps.chat.models import Chat, ChatStatus, Message, MessageStatus
from apps.chat.selectors import counterpart_messages
from apps.core.db import ClockTimestamp
from apps.core.db_errors import UNIQUE_VIOLATION, db_error_details
from apps.core.transactions import transactional
from apps.notifications import events
from apps.notifications.services import mark_chat_read
from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied

CHAT_CLOSED = "Esta conversa está encerrada e não aceita novas mensagens."


@transactional
def open_chat(client_id: int, workshop_id: int) -> tuple[Chat, bool]:
    """Obtém ou cria a conversa do par (idempotente, inclusive sob concorrência).

    `uq_chat_client_workshop` (BE-009) garante um só chat: a segunda criação
    simultânea espera a primeira, recebe 23505 e relê o chat confirmado.
    """
    if not Workshop.objects.filter(
        pk=workshop_id, status=AccountStatus.ACTIVE
    ).exists():
        raise NotFound("Oficina não encontrada.")

    existing = Chat.objects.filter(client_id=client_id, workshop_id=workshop_id).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            return Chat.objects.create(
                client_id=client_id, workshop_id=workshop_id
            ), True
    except IntegrityError as exc:
        if db_error_details(exc)[0] != UNIQUE_VIOLATION:
            raise
    return Chat.objects.get(client_id=client_id, workshop_id=workshop_id), False


@transactional
def send_message(chat: Chat, role: str, account_id: int, content: str) -> Message:
    """Remetente = sessão. `date_sent` = clock_timestamp() do INSERT (não o início da
    transação), para que o polling com `after` inclusivo não perca mensagens."""
    if chat.status_chat != ChatStatus.ACTIVE:
        raise PermissionDenied(CHAT_CLOSED)
    sender = (
        {"sender_client_id": account_id}
        if role == "client"
        else {"sender_workshop_id": account_id}
    )
    message = Message.objects.create(
        chat=chat, content=content, date_sent=ClockTimestamp(), **sender
    )
    message.refresh_from_db()
    events.message_sent(message, chat, role)
    return message


def mark_delivered(chat: Chat, role: str) -> int:
    """Leitura da conversa: mensagens do interlocutor ainda `sent` passam a `delivered`."""
    return (
        counterpart_messages(role)
        .filter(chat=chat, status_message=MessageStatus.SENT)
        .update(status_message=MessageStatus.DELIVERED)
    )


@transactional
def mark_read(chat: Chat, role: str) -> int:
    """Marca como lidas só as mensagens do interlocutor (as próprias não mudam) e
    o aviso da conversa no sino de quem leu."""
    updated = (
        counterpart_messages(role)
        .filter(chat=chat)
        .exclude(status_message=MessageStatus.READ)
        .update(status_message=MessageStatus.READ)
    )
    reader_id = chat.client_id if role == "client" else chat.workshop_id
    mark_chat_read(role, reader_id, chat.pk)
    return updated
