"""Rotas `/api/admin/*`: moderação de denúncias (BE-073) e de serviços personalizados (BE-074).

Só admin (`is_staff`, DP-03): visitante → 401, cliente/oficina → 403. Toda escrita
é auditada no logger `sam.audit` (quem, ação, alvo, status HTTP e transição).
"""

from apps.catalog.models import WorkshopService
from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.moderation.audit import log_admin_action
from apps.moderation.filters import DenunciationFilter, ServiceRequestFilter
from apps.moderation.permissions import ADMIN_PERMISSIONS
from apps.moderation.serializers import (
    AdminDenunciationSerializer,
    AdminReviewSerializer,
    DenunciationModerationSerializer,
    ServiceRequestApproveSerializer,
    ServiceRequestRejectSerializer,
    ServiceRequestSerializer,
)
from apps.moderation.services import (
    DENUNCIATION_RELATED,
    approve_service_request,
    hide_review,
    moderate_denunciation,
    reject_service_request,
)
from apps.reviews.models import Denunciation, Review
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView


class AdminViewMixin:
    """Base das rotas `/api/admin/*` (BE-035).

    Exige admin (`is_staff`): visitante → 401, cliente/oficina → 403. Toda
    requisição de escrita de um admin é registrada no log de auditoria.
    Coloque antes da classe genérica do DRF: `class X(AdminViewMixin, ListAPIView)`.

    `audit_action` nomeia a ação no log e `audit_target_type` o tipo do alvo (o id
    vem do kwarg da rota); a view pode pôr detalhes em `self.audit_extra` (ex.: a
    transição de status). Um teste percorre o URLconf e exige este mixin em toda
    rota `/api/admin/*`.
    """

    permission_classes = ADMIN_PERMISSIONS
    audit_action = None
    audit_target_type = None

    def get_audit_target(self):
        lookup = getattr(self, "lookup_url_kwarg", None) or getattr(
            self, "lookup_field", "pk"
        )
        return self.audit_target_type, getattr(self, "kwargs", {}).get(lookup)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        user = getattr(request, "user", None)
        if request.method not in SAFE_METHODS and getattr(user, "is_staff", False):
            target_type, target_id = self.get_audit_target()
            log_admin_action(
                request,
                self.audit_action or type(self).__name__,
                target_type=target_type,
                target_id=None if target_id is None else str(target_id),
                status=response.status_code,
                **(getattr(self, "audit_extra", None) or {}),
            )
        return response


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


STATUS_PARAM = OpenApiParameter(
    "status", OpenApiTypes.STR, description="Lista separada por vírgula."
)


# ----------------------------------------------------------------- BE-073


def _denunciations():
    return Denunciation.objects.select_related(
        *DENUNCIATION_RELATED, "review__budget__attendance__client"
    ).order_by("date_creation", "id_denunciation")


@extend_schema_view(
    get=extend_schema(
        summary="Fila de denúncias",
        description="Mais antigas primeiro. `?status=pending,in_review` filtra a fila em aberto; "
        "`?target_type=review|promotion|advertisement`.",
        parameters=[STATUS_PARAM],
        responses={
            200: AdminDenunciationSerializer(many=True),
            **_errors(400, 401, 403),
        },
    )
)
class AdminDenunciationListView(AdminViewMixin, generics.ListAPIView):
    """BE-073: `GET /admin/denunciations/`."""

    serializer_class = AdminDenunciationSerializer
    filterset_class = DenunciationFilter
    queryset = Denunciation.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return _denunciations()


@extend_schema_view(
    get=extend_schema(summary="Detalhe de uma denúncia"),
    patch=extend_schema(
        summary="Analisa (in_review) ou resolve (upheld/dismissed) uma denúncia",
        description="Resolver exige `moderation_decision` (400). Denúncia já resolvida ou o mesmo "
        "status → 409. `upheld` tira o conteúdo do ar: avaliação → `hidden`; promoção → "
        "`inactive` (divulgações canceladas; pagas vão para estorno); divulgação → `cancelled`. "
        "O denunciante é notificado da resolução.",
        request=DenunciationModerationSerializer,
        responses={
            200: AdminDenunciationSerializer,
            **_errors(400, 401, 403, 404, 409),
        },
    ),
)
class AdminDenunciationDetailView(AdminViewMixin, generics.RetrieveAPIView):
    """BE-073: `GET/PATCH /admin/denunciations/{id}/`."""

    serializer_class = AdminDenunciationSerializer
    queryset = Denunciation.objects.none()
    lookup_url_kwarg = (
        "id"  # nome do parâmetro no OpenAPI (sem isto sairia `id_denunciation`, P-22)
    )
    audit_action = "denunciation.moderate"
    audit_target_type = "denunciation"
    http_method_names = ["get", "patch", "options"]

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return _denunciations()

    def patch(self, request, id):
        serializer = DenunciationModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data["status_denunciation"]
        previous = (
            Denunciation.objects.filter(pk=id)
            .values_list("status_denunciation", flat=True)
            .first()
        )
        self.audit_extra = {"from_status": previous, "to_status": target}
        moderate_denunciation(
            id,
            status=target,
            decision=serializer.validated_data.get("moderation_decision"),
        )
        return Response(self.get_serializer(_denunciations().get(pk=id)).data)


class AdminReviewHideView(AdminViewMixin, APIView):
    """BE-073: `POST /admin/reviews/{id}/hide/`."""

    audit_action = "review.hide"
    audit_target_type = "review"

    @extend_schema(
        summary="Oculta uma avaliação (status_review = hidden)",
        description="Idempotente. A avaliação some do perfil público, da nota média e do mapa.",
        request=None,
        responses={200: AdminReviewSerializer, **_errors(401, 403, 404)},
    )
    def post(self, request, pk):
        hide_review(pk)
        review = Review.objects.select_related(
            "budget__workshop", "budget__attendance__client"
        ).get(pk=pk)
        return Response(AdminReviewSerializer(review).data)


# ----------------------------------------------------------------- BE-074


def _service_requests():
    return (
        WorkshopService.objects.filter(status_solicitation__isnull=False)
        .select_related("workshop", "service__category", "suggested_category")
        .order_by("created_at", "id_workshop_service")
    )


@extend_schema_view(
    get=extend_schema(
        summary="Solicitações de serviço personalizado",
        description="Sem `status`, só as pendentes (mais antigas primeiro). "
        "`?status=pending,approved,rejected` mostra também as decididas.",
        parameters=[STATUS_PARAM],
        responses={200: ServiceRequestSerializer(many=True), **_errors(400, 401, 403)},
    )
)
class AdminServiceRequestListView(AdminViewMixin, generics.ListAPIView):
    """BE-074: `GET /admin/service-requests/`."""

    serializer_class = ServiceRequestSerializer
    filterset_class = ServiceRequestFilter
    queryset = WorkshopService.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return _service_requests()


class _ServiceRequestAction(AdminViewMixin, APIView):
    """BE-074: aprovar/rejeitar uma solicitação."""

    audit_target_type = "service_request"

    def request_response(self, pk):
        return Response(ServiceRequestSerializer(_service_requests().get(pk=pk)).data)


class AdminServiceRequestApproveView(_ServiceRequestAction):
    audit_action = "service_request.approve"

    @extend_schema(
        summary="Aprova a solicitação (approve_workshop_service_request)",
        description="Reaproveita o serviço global de mesmo nome normalizado sem alterá-lo; senão "
        "cria um com `name`/`description`/`id_category` (ou os da oficina). Categoria obrigatória "
        "para serviço novo (400). Já decidida ou a oficina já tem o serviço global → 409.",
        request=ServiceRequestApproveSerializer,
        responses={200: ServiceRequestSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request, pk):
        serializer = ServiceRequestApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        approve_service_request(
            pk,
            category_id=data.get("id_category"),
            name=data.get("name"),
            description=data.get("description"),
        )
        return self.request_response(pk)


class AdminServiceRequestRejectView(_ServiceRequestAction):
    audit_action = "service_request.reject"

    @extend_schema(
        summary="Rejeita a solicitação (reject_workshop_service_request)",
        description="`motivation` obrigatório (400). O serviço continua só no catálogo da oficina. "
        "Já decidida → 409.",
        request=ServiceRequestRejectSerializer,
        responses={200: ServiceRequestSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request, pk):
        serializer = ServiceRequestRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reject_service_request(pk, motivation=serializer.validated_data["motivation"])
        return self.request_response(pk)
