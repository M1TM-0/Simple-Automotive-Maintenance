"""Notificações do usuário logado (BE-069): listar, contar e marcar como lidas.

Cliente e oficina (oficina mesmo no assistente: o sino aparece em todas as telas
logadas). Notificação de outro usuário não existe para a view → 404.
"""

from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.core.permissions import IsAccountHolder
from apps.core.throttles import PollingRateThrottle
from apps.notifications.models import Notification
from apps.notifications.serializers import (
    NotificationQuerySerializer,
    NotificationSerializer,
    UnreadCountSerializer,
)
from apps.notifications.services import for_recipient, mark_all_read, mark_read
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

NO_CONTENT = OpenApiResponse(description="Sem conteúdo.")


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


@extend_schema_view(
    get=extend_schema(
        summary="Notificações do usuário (mais recentes primeiro)",
        parameters=[NotificationQuerySerializer],
        responses={200: NotificationSerializer(many=True), **_errors(400, 401, 403)},
    )
)
class NotificationListView(generics.ListAPIView):
    permission_classes = [IsAccountHolder]
    serializer_class = NotificationSerializer
    queryset = Notification.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        params = NotificationQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        user = self.request.user
        queryset = for_recipient(user.role, user.id)
        if params.validated_data["unread"]:
            queryset = queryset.filter(read_status=False)
        return queryset.order_by("-date_creation", "-id_notification")


class UnreadCountView(APIView):
    """Contador do sino (poll de 60 s): uma consulta agregada no índice do destinatário."""

    permission_classes = [IsAccountHolder]
    throttle_classes = [PollingRateThrottle]

    @extend_schema(
        summary="Quantidade de notificações não lidas",
        responses={200: UnreadCountSerializer, **_errors(401, 403, 429)},
    )
    def get(self, request):
        count = (
            for_recipient(request.user.role, request.user.id)
            .filter(read_status=False)
            .count()
        )
        return Response({"count": count})


class NotificationReadView(APIView):
    permission_classes = [IsAccountHolder]

    @extend_schema(
        summary="Marca uma notificação como lida",
        request=None,
        responses={204: NO_CONTENT, **_errors(401, 403, 404)},
    )
    def post(self, request, pk):
        if not mark_read(request.user.role, request.user.id, pk):
            raise NotFound("Notificação não encontrada.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationReadAllView(APIView):
    permission_classes = [IsAccountHolder]

    @extend_schema(
        summary="Marca todas as notificações como lidas",
        request=None,
        responses={204: NO_CONTENT, **_errors(401, 403)},
    )
    def post(self, request):
        mark_all_read(request.user.role, request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
