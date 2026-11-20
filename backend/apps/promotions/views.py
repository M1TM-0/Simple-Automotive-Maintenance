"""Promoções e divulgações: da oficina (BE-063, BE-064) e vitrine pública (BE-066, BE-068)."""

from apps.core.mixins import (
    OwnedByWorkshopMixin,
    PublicCacheMixin,
    is_schema_generation,
)
from apps.core.openapi import ERROR_RESPONSES
from apps.core.pagination import SamPagination
from apps.core.permissions import WORKSHOP_PERMISSIONS
from apps.promotions.models import Promotion, PromotionEffective
from apps.promotions.selectors import (
    on_air,
    promotion_advertisements,
    workshop_promotions,
)
from apps.promotions.serializers import (
    AdvertisementCreateSerializer,
    AdvertisementSerializer,
    PromotionSerializer,
    PromotionWriteSerializer,
    PublicPromotionSerializer,
)
from apps.promotions.services import (
    create_promotion,
    request_advertisement,
    update_promotion,
)
from apps.workshops.selectors import public_workshop_or_404
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

MULTIPART = {
    "multipart/form-data": PromotionWriteSerializer,
    "application/json": PromotionWriteSerializer,
}


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


class _WorkshopPromotions:
    permission_classes = WORKSHOP_PERMISSIONS
    serializer_class = PromotionSerializer
    queryset = PromotionEffective.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return workshop_promotions(self.request.user.id)

    def promotion_response(self, pk, status_code=status.HTTP_200_OK):
        instance = self.get_queryset().get(pk=pk)
        return Response(
            PromotionSerializer(instance, context=self.get_serializer_context()).data,
            status=status_code,
        )


@extend_schema_view(
    get=extend_schema(
        summary="Promoções da oficina (com effective_status e is_valid_now)"
    ),
    post=extend_schema(
        summary="Cria promoção (multipart)",
        request=MULTIPART,
        responses={201: PromotionSerializer, **_errors(400, 401, 403)},
    ),
)
class WorkshopPromotionListCreateView(_WorkshopPromotions, generics.ListCreateAPIView):
    """BE-063."""

    def create(self, request, *args, **kwargs):
        serializer = PromotionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        promotion = create_promotion(request.user.id, serializer.validated_data)
        return self.promotion_response(promotion.pk, status.HTTP_201_CREATED)


class WorkshopPromotionDetailView(_WorkshopPromotions, generics.GenericAPIView):
    """BE-063: edita/ativa/desativa; expirada → 409."""

    @extend_schema(
        summary="Edita/ativa/desativa promoção (expirada é imutável)",
        request=MULTIPART,
        responses={200: PromotionSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def patch(self, request, pk):
        promotion = get_object_or_404(Promotion, pk=pk, workshop_id=request.user.id)
        serializer = PromotionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_promotion(promotion, serializer.validated_data)
        return self.promotion_response(pk)


@extend_schema_view(
    get=extend_schema(summary="Divulgações contratadas da promoção"),
    post=extend_schema(
        summary="Solicita divulgação (nasce pending/pending, preço calculado pelo servidor)",
        request={"multipart/form-data": AdvertisementCreateSerializer},
        responses={
            201: AdvertisementSerializer,
            400: ERROR_RESPONSES[400],
            409: OpenApiResponse(description="Promoção não está ativa."),
            **_errors(401, 403, 404),
        },
    ),
)
class WorkshopAdvertisementListCreateView(
    OwnedByWorkshopMixin, generics.ListCreateAPIView
):
    """BE-064."""

    permission_classes = WORKSHOP_PERMISSIONS
    serializer_class = AdvertisementSerializer
    queryset = Promotion.objects.all()

    def get_promotion(self):
        return get_object_or_404(super().get_queryset(), pk=self.kwargs["pk"])

    def get_queryset(self):
        if is_schema_generation(self):
            return Promotion.objects.none()
        return promotion_advertisements(self.get_promotion().pk)

    def create(self, request, *args, **kwargs):
        promotion = self.get_promotion()
        serializer = AdvertisementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        advertisement = request_advertisement(promotion, serializer.validated_data)
        instance = promotion_advertisements(promotion.pk).get(pk=advertisement.pk)
        return Response(
            AdvertisementSerializer(
                instance, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------ público (BE-066, BE-068)


class OnAirPagination(SamPagination):
    """Home e mapa leem só a 1ª página: até 50 itens por padrão."""

    page_size = 50


@extend_schema_view(
    get=extend_schema(
        summary="Promoções e divulgações no ar (home e mapa)",
        description=(
            "Público. Une promoções vigentes (`kind=promotion`, `vw_promotion_effective."
            "is_valid_now`) e divulgações em execução (`kind=advertisement`, "
            "`vw_advertisement_effective.is_running_now`) de oficinas públicas. "
            "Divulgações primeiro, depois promoções pela data de término. "
            "`active=true` é aceito por compatibilidade: a lista pública só tem o que "
            "está no ar. Cache público de 30 s."
        ),
        parameters=[OpenApiParameter("active", OpenApiTypes.BOOL)],
    )
)
class PublicPromotionListView(PublicCacheMixin, generics.ListAPIView):
    """BE-068: `GET /promotions/`."""

    cache_max_age = 30
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicPromotionSerializer
    pagination_class = OnAirPagination
    queryset = Promotion.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return on_air()


@extend_schema_view(
    get=extend_schema(
        summary="Promoções vigentes da oficina (público)",
        description="Mesma forma de `GET /promotions/`, só `kind=promotion`. Oficina não pública → 404.",
        responses={
            200: PublicPromotionSerializer(many=True),
            404: ERROR_RESPONSES[404],
        },
    )
)
class PublicWorkshopPromotionListView(PublicCacheMixin, generics.ListAPIView):
    """BE-066: `GET /workshops/{id}/promotions/`."""

    cache_max_age = 30
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicPromotionSerializer
    queryset = Promotion.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        workshop = public_workshop_or_404(self.kwargs["workshop_id"])
        return on_air(workshop.pk, include_advertisements=False)
