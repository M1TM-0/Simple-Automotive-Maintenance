"""Chat: conversas (BE-057) e mensagens com polling (BE-058).

Só os dois participantes alcançam a conversa: o queryset é filtrado pela sessão,
então um chat de outro par responde 404.
"""

import re

from apps.chat.models import Chat
from apps.chat.selectors import chats_for
from apps.chat.serializers import (
    ChatSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from apps.chat.services import mark_delivered, mark_read, open_chat, send_message
from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.core.pagination import SamPagination
from apps.core.permissions import IsChatParticipant, IsClient
from apps.core.throttles import MessageRateThrottle, PollingRateThrottle
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


class _ParticipantChats:
    permission_classes = [IsChatParticipant]
    serializer_class = ChatSerializer
    queryset = Chat.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        user = self.request.user
        return chats_for(user.role, user.id)

    def get_chat(self, pk):
        """Conversa do participante (sem as anotações da lista)."""
        user = self.request.user
        owner = (
            {"client_id": user.id}
            if user.role == "client"
            else {"workshop_id": user.id}
        )
        return get_object_or_404(Chat, pk=pk, **owner)


@extend_schema_view(
    get=extend_schema(summary="Conversas do usuário (só o interlocutor é enviado)")
)
class ChatListView(_ParticipantChats, generics.ListAPIView):
    """BE-057: ordenadas pela última mensagem."""


@extend_schema_view(
    get=extend_schema(
        summary="Detalhe de uma conversa",
        responses={200: ChatSerializer, **_errors(401, 403, 404)},
    )
)
class ChatDetailView(_ParticipantChats, generics.RetrieveAPIView):
    """BE-057."""


class ChatOpenView(APIView):
    """BE-057: `POST /chats/{id_workshop}/open/` — só o cliente abre conversa."""

    permission_classes = [IsClient]

    @extend_schema(
        summary="Obtém ou cria a conversa com a oficina (idempotente)",
        description="201 quando cria; 200 quando a conversa já existia.",
        request=None,
        responses={200: ChatSerializer, 201: ChatSerializer, **_errors(401, 403, 404)},
    )
    def post(self, request, workshop_id):
        chat, created = open_chat(request.user.id, workshop_id)
        instance = chats_for("client", request.user.id).get(pk=chat.pk)
        return Response(
            ChatSerializer(instance, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _parse_after(raw):
    if not raw:
        return None
    # "+03:00" sem URL-encoding chega como " 03:00": restaura só o sinal do fuso.
    try:
        value = parse_datetime(re.sub(r" (\d{2}:?\d{2})$", r"+\1", raw.strip()))
    except ValueError:  # formato certo, data impossível (ex.: mês 13) — BE-086
        value = None
    if value is None:
        raise ValidationError(
            {"after": ["Data inválida. Use ISO-8601 (ex.: 2026-11-17T18:00:00Z)."]}
        )
    return make_aware(value) if is_naive(value) else value


class ChatMessagesView(_ParticipantChats, generics.GenericAPIView):
    """BE-058. Polling de 5 s com `?after=<date_sent>` (inclusivo: `date_sent >= after`).

    Sem `after`, a página 1 traz as mensagens **mais recentes** (as páginas seguintes
    voltam no tempo); com `after`, a página 1 traz as primeiras a partir dele. Em
    ambos os casos `results` vem em ordem cronológica.
    """

    serializer_class = MessageSerializer
    throttle_classes = [MessageRateThrottle, PollingRateThrottle]

    @extend_schema(
        summary="Mensagens (ordem cronológica; polling com ?after)",
        parameters=[
            OpenApiParameter("after", OpenApiTypes.DATETIME, description="Inclusivo.")
        ],
        responses={
            200: MessageSerializer(many=True),
            **_errors(400, 401, 403, 404, 429),
        },
    )
    def get(self, request, pk):
        chat = self.get_chat(pk)
        after = _parse_after(request.query_params.get("after"))
        mark_delivered(chat, request.user.role)

        messages = chat.messages.all()
        paginator = SamPagination()
        if after is not None:
            queryset = messages.filter(date_sent__gte=after).order_by(
                "date_sent", "id_message"
            )
            page = paginator.paginate_queryset(queryset, request, view=self)
        else:
            queryset = messages.order_by("-date_sent", "-id_message")
            page = list(
                reversed(paginator.paginate_queryset(queryset, request, view=self))
            )
        data = MessageSerializer(
            page, many=True, context=self.get_serializer_context()
        ).data
        return paginator.get_paginated_response(data)

    @extend_schema(
        summary="Envia mensagem de texto",
        request=MessageCreateSerializer,
        responses={201: MessageSerializer, **_errors(400, 401, 403, 404, 429)},
    )
    def post(self, request, pk):
        chat = self.get_chat(pk)
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = send_message(
            chat,
            request.user.role,
            request.user.id,
            serializer.validated_data["content"],
        )
        return Response(
            MessageSerializer(message, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ChatReadView(_ParticipantChats, APIView):
    """BE-058: marca como lidas as mensagens do interlocutor."""

    @extend_schema(
        summary="Marca como lidas as mensagens do interlocutor",
        request=None,
        responses={204: None, **_errors(401, 403, 404)},
    )
    def post(self, request, pk):
        mark_read(self.get_chat(pk), request.user.role)
        return Response(status=status.HTTP_204_NO_CONTENT)
