"""Chat (BE-057, BE-058): a resposta traz só o interlocutor (RI-13)."""

from apps.core import limits
from apps.core.fields import media_url
from apps.core.openapi import optional_response_fields
from rest_framework import serializers

MAX_MESSAGE_LENGTH = limits.MESSAGE


def _role(context):
    request = context.get("request")
    return getattr(getattr(request, "user", None), "role", None)


@optional_response_fields("workshop", "client")
class ChatSerializer(serializers.Serializer):
    """Cliente recebe `workshop{id,name_fantasy,photo_profile}`; oficina recebe
    `client{id,name,photo_profile}`; nunca os dois."""

    id = serializers.IntegerField(source="pk")
    status_chat = serializers.CharField()
    date_creation = serializers.DateTimeField()
    workshop = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField()
    open_attendance = serializers.SerializerMethodField(
        help_text="Atendimento não finalizado mais recente do par, ou null."
    )

    def get_workshop(self, obj) -> dict | None:
        if _role(self.context) != "client":
            return None
        page = getattr(obj.workshop, "page", None)
        return {
            "id": obj.workshop_id,
            "name_fantasy": obj.workshop.name_fantasy,
            "photo_profile": media_url(
                page.photo_profile if page else None, self.context.get("request")
            ),
        }

    def get_client(self, obj) -> dict | None:
        if _role(self.context) != "workshop":
            return None
        return {
            "id": obj.client_id,
            "name": obj.client.name,
            "photo_profile": media_url(
                obj.client.photo_profile, self.context.get("request")
            ),
        }

    def get_last_message(self, obj) -> dict | None:
        if obj.last_date is None:
            return None
        return {
            "content": obj.last_content,
            "date_sent": serializers.DateTimeField().to_representation(obj.last_date),
            "sender": "client" if obj.last_sender_client is not None else "workshop",
        }

    def get_open_attendance(self, obj) -> dict | None:
        if obj.open_attendance_id is None:
            return None
        return {
            "id": obj.open_attendance_id,
            "status_attendance": obj.open_attendance_status,
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("workshop" if _role(self.context) != "client" else "client")
        return data


class MessageSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    content = serializers.CharField(read_only=True)
    date_sent = serializers.DateTimeField(read_only=True)
    status_message = serializers.CharField(read_only=True)
    sender = serializers.SerializerMethodField(help_text="`client` ou `workshop`.")
    mine = serializers.SerializerMethodField()

    def get_sender(self, obj) -> str:
        return "client" if obj.sender_client_id is not None else "workshop"

    def get_mine(self, obj) -> bool:
        return self.get_sender(obj) == _role(self.context)


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=MAX_MESSAGE_LENGTH)
