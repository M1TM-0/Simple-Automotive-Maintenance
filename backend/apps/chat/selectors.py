"""Leituras do chat com número fixo de queries (o frontend faz polling de 5 s)."""

from apps.attendances.models import Attendance, AttendanceStatus
from apps.chat.models import Chat, Message, MessageStatus
from django.db.models import Count, F, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

FINAL_ATTENDANCE = (AttendanceStatus.DELIVERED, AttendanceStatus.CANCELED)


def counterpart_messages(role: str):
    """Mensagens enviadas pelo interlocutor de quem tem o perfil `role`."""
    if role == "client":
        return Message.objects.filter(sender_workshop__isnull=False)
    return Message.objects.filter(sender_client__isnull=False)


def chats_for(role: str, account_id: int):
    owner = (
        {"client_id": account_id} if role == "client" else {"workshop_id": account_id}
    )
    last = Message.objects.filter(chat_id=OuterRef("pk")).order_by(
        "-date_sent", "-id_message"
    )
    unread = (
        counterpart_messages(role)
        .filter(chat_id=OuterRef("pk"))
        .exclude(status_message=MessageStatus.READ)
        .order_by()
        .values("chat_id")
        .annotate(total=Count("id_message"))
        .values("total")
    )
    open_attendance = (
        Attendance.objects.filter(
            client_id=OuterRef("client_id"), workshop_id=OuterRef("workshop_id")
        )
        .exclude(status_attendance__in=FINAL_ATTENDANCE)
        .order_by("-date_attendance", "-id_attendance")
    )
    return (
        Chat.objects.filter(**owner)
        .select_related("workshop__page", "client")
        .annotate(
            last_content=Subquery(last.values("content")[:1]),
            last_date=Subquery(last.values("date_sent")[:1]),
            last_sender_client=Subquery(last.values("sender_client_id")[:1]),
            unread_count=Coalesce(
                Subquery(unread[:1]), Value(0), output_field=IntegerField()
            ),
            open_attendance_id=Subquery(open_attendance.values("pk")[:1]),
            open_attendance_status=Subquery(
                open_attendance.values("status_attendance")[:1]
            ),
        )
        .order_by(F("last_date").desc(nulls_last=True), "-date_creation", "-id_chat")
    )
