"""Avaliações (cliente avalia; oficina lista e responde; lista pública) e denúncias."""

from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.core.permissions import WORKSHOP_PERMISSIONS, IsClient
from apps.reviews.models import Review, ReviewStatus
from apps.reviews.serializers import (
    DenunciationCreateSerializer,
    DenunciationSerializer,
    PublicReviewSerializer,
    ReviewCreateSerializer,
    ReviewResponseSerializer,
    ReviewSerializer,
    WorkshopReviewSerializer,
)
from apps.reviews.services import create_denunciation, create_review, respond_review
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


class ReviewCreateView(APIView):
    """BE-059."""

    permission_classes = [IsClient]

    @extend_schema(
        summary="Cliente avalia atendimento entregue (por orçamento aprovado)",
        request=ReviewCreateSerializer,
        responses={201: ReviewSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = create_review(request.user.id, serializer.validated_data)
        review = Review.objects.select_related("budget").get(pk=review.pk)
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


def _workshop_reviews(workshop_id):
    return Review.objects.filter(budget__workshop_id=workshop_id).select_related(
        "budget__attendance__client"
    )


@extend_schema_view(
    get=extend_schema(summary="Avaliações recebidas (inclui ocultas e em análise)")
)
class WorkshopReviewListView(generics.ListAPIView):
    """BE-060."""

    permission_classes = WORKSHOP_PERMISSIONS
    serializer_class = WorkshopReviewSerializer
    queryset = Review.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return _workshop_reviews(self.request.user.id).order_by(
            "-date_creation", "id_review"
        )


class WorkshopReviewResponseView(APIView):
    """BE-060: avaliação de outra oficina → 404; oculta → 409."""

    permission_classes = WORKSHOP_PERMISSIONS

    @extend_schema(
        summary="Responde ou edita a resposta pública da avaliação",
        request=ReviewResponseSerializer,
        responses={200: WorkshopReviewSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request, pk):
        review = get_object_or_404(_workshop_reviews(request.user.id), pk=pk)
        serializer = ReviewResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        respond_review(review, serializer.validated_data["workshop_response"])
        return Response(
            WorkshopReviewSerializer(_workshop_reviews(request.user.id).get(pk=pk)).data
        )


class DenunciationCreateView(APIView):
    """BE-061."""

    permission_classes = [IsClient]

    @extend_schema(
        summary="Cliente denuncia avaliação, promoção ou divulgação",
        request=DenunciationCreateSerializer,
        responses={201: DenunciationSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request):
        serializer = DenunciationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        denunciation = create_denunciation(request.user.id, serializer.validated_data)
        denunciation.refresh_from_db()
        return Response(
            DenunciationSerializer(denunciation).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    get=extend_schema(
        summary="Avaliações publicadas da oficina (público)",
        description="Só `published` (ocultas e em análise não aparecem), mais recentes primeiro. "
        "Autor abreviado (DP-15). Oficina não pública → 404.",
        responses={200: PublicReviewSerializer(many=True), 404: ERROR_RESPONSES[404]},
    )
)
class PublicWorkshopReviewListView(generics.ListAPIView):
    """BE-066: `GET /workshops/{id}/reviews/`."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicReviewSerializer
    queryset = Review.objects.none()

    def get_queryset(self):
        from apps.workshops.selectors import public_workshop_or_404

        if is_schema_generation(self):
            return self.queryset
        workshop = public_workshop_or_404(self.kwargs["workshop_id"])
        return (
            _workshop_reviews(workshop.pk)
            .filter(status_review=ReviewStatus.PUBLISHED)
            .order_by("-date_creation", "id_review")
        )
