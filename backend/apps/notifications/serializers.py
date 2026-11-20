"""Notificações do usuário logado (BE-069)."""

from apps.notifications.services import safe_url
from rest_framework import serializers


class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk", read_only=True)
    title = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    date_creation = serializers.DateTimeField(read_only=True)
    read_status = serializers.BooleanField(read_only=True)
    url = serializers.SerializerMethodField(
        help_text="Página `.html` do projeto (ex.: `attendance.html?id=12`) ou `null`."
    )

    def get_url(self, obj) -> str | None:
        return safe_url(obj.url)


class UnreadCountSerializer(serializers.Serializer):
    count = serializers.IntegerField()


class NotificationQuerySerializer(serializers.Serializer):
    unread = serializers.BooleanField(
        required=False, default=False, help_text="`true` = só as não lidas."
    )
