from apps.core.db import CurrentTimestamp
from django.db import models


class ChatStatus(models.TextChoices):
    ACTIVE = "active", "Ativa"
    ARCHIVED = "archived", "Arquivada"
    CLOSED = "closed", "Encerrada"


class MessageStatus(models.TextChoices):
    SENT = "sent", "Enviada"
    DELIVERED = "delivered", "Entregue"
    READ = "read", "Lida"


class Chat(models.Model):
    id_chat = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(
        "accounts.Client",
        db_column="id_client",
        on_delete=models.DO_NOTHING,
        related_name="chats",
    )
    workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        on_delete=models.DO_NOTHING,
        related_name="chats",
    )
    date_creation = models.DateTimeField(db_default=CurrentTimestamp())
    status_chat = models.CharField(
        max_length=50,
        choices=ChatStatus.choices,
        db_default=ChatStatus.ACTIVE.value,
    )

    class Meta:
        db_table = "chat"
        managed = False


class Message(models.Model):
    id_message = models.BigAutoField(primary_key=True)
    chat = models.ForeignKey(
        Chat,
        db_column="id_chat",
        on_delete=models.DO_NOTHING,
        related_name="messages",
    )
    sender_client = models.ForeignKey(
        "accounts.Client",
        db_column="id_client",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="sent_messages",
    )
    sender_workshop = models.ForeignKey(
        "accounts.Workshop",
        db_column="id_workshop",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        related_name="sent_messages",
    )
    content = models.TextField()
    date_sent = models.DateTimeField(db_default=CurrentTimestamp())
    status_message = models.CharField(
        max_length=50,
        choices=MessageStatus.choices,
        db_default=MessageStatus.SENT.value,
    )

    class Meta:
        db_table = "message"
        managed = False
