"""Catálogo global (público) e catálogo da oficina (serviços e produtos)."""

from apps.catalog.models import Product, Service, ServiceCategory, WorkshopService
from apps.catalog.serializers import (
    ProductSerializer,
    ProductWriteSerializer,
    PublicProductSerializer,
    ServiceCategorySerializer,
    ServiceSerializer,
    WorkshopServiceCreateSerializer,
    WorkshopServiceSerializer,
    WorkshopServiceUpdateSerializer,
)
from apps.catalog.services import (
    add_workshop_service,
    create_product,
    update_product,
    update_workshop_service,
)
from apps.core.mixins import OwnedByWorkshopMixin, PublicCacheMixin
from apps.core.openapi import ERROR_RESPONSES
from apps.core.permissions import WORKSHOP_PERMISSIONS, WORKSHOP_WIZARD_PERMISSIONS
from apps.core.search import search_filter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# ------------------------------------------------------- catálogo global (BE-036)


@extend_schema_view(get=extend_schema(summary="Categorias de serviço (público)"))
class ServiceCategoryListView(PublicCacheMixin, generics.ListAPIView):
    queryset = ServiceCategory.objects.order_by("name", "id_service_category")
    serializer_class = ServiceCategorySerializer
    permission_classes = [AllowAny]
    authentication_classes = []


@extend_schema_view(
    get=extend_schema(
        summary="Serviços ativos do catálogo global (público)",
        description=(
            "`q` busca no nome por texto normalizado (sem diferenciar maiúsculas nem "
            "acentos: `oleo` encontra “Troca de óleo”). `category` = id da categoria."
        ),
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, description="Texto do nome."),
            OpenApiParameter(
                "category", OpenApiTypes.INT, description="Id da categoria."
            ),
        ],
        responses={200: ServiceSerializer(many=True), 400: ERROR_RESPONSES[400]},
    )
)
class ServiceListView(PublicCacheMixin, generics.ListAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_queryset(self):
        queryset = Service.objects.filter(active=True).select_related("category")
        params = self.request.query_params

        category = params.get("category")
        if category:
            if not category.isdigit():
                raise ValidationError({"category": ["Categoria inválida."]})
            queryset = queryset.filter(category_id=int(category))

        queryset = search_filter(queryset, params.get("q"), "name")
        return queryset.order_by("name", "id_service")


# --------------------------------------------------- serviços da oficina (BE-041)


class _WorkshopServiceQueryset(OwnedByWorkshopMixin):
    queryset = WorkshopService.objects.select_related(
        "service__category", "suggested_category"
    )


@extend_schema_view(
    get=extend_schema(summary="Serviços da oficina (catálogo global e personalizados)"),
    post=extend_schema(
        summary="Adiciona serviço do catálogo ou personalizado (gera solicitação)",
        request=WorkshopServiceCreateSerializer,
        responses={
            201: WorkshopServiceSerializer,
            **{k: ERROR_RESPONSES[k] for k in (400, 401, 403, 409)},
        },
    ),
)
class WorkshopServiceListCreateView(
    _WorkshopServiceQueryset, generics.ListCreateAPIView
):
    """Rota do assistente T17: exige o perfil oficina, mas não o cadastro concluído
    (é cadastrando o primeiro serviço que a oficina conclui o cadastro, BE-028)."""

    permission_classes = WORKSHOP_WIZARD_PERMISSIONS
    serializer_class = WorkshopServiceSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("id_workshop_service")

    def create(self, request, *args, **kwargs):
        serializer = WorkshopServiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = add_workshop_service(request.user.id, serializer.validated_data)
        instance = self.get_queryset().get(pk=created.pk)
        return Response(
            WorkshopServiceSerializer(instance).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    patch=extend_schema(
        summary="Edita preço, duração, descrição local e disponibilidade",
        request=WorkshopServiceUpdateSerializer,
        responses={
            200: WorkshopServiceSerializer,
            **{k: ERROR_RESPONSES[k] for k in (400, 401, 403, 404)},
        },
    )
)
class WorkshopServiceDetailView(_WorkshopServiceQueryset, generics.GenericAPIView):
    permission_classes = WORKSHOP_WIZARD_PERMISSIONS
    serializer_class = WorkshopServiceSerializer

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = WorkshopServiceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_workshop_service(instance, serializer.validated_data)
        return Response(WorkshopServiceSerializer(self.get_object()).data)


# ------------------------------------------------------------ produtos (BE-042)


@extend_schema_view(
    get=extend_schema(summary="Produtos da oficina (inclui inativos)"),
    post=extend_schema(
        summary="Cadastra produto (multipart)",
        request={
            "multipart/form-data": ProductWriteSerializer,
            "application/json": ProductWriteSerializer,
        },
        responses={
            201: ProductSerializer,
            **{k: ERROR_RESPONSES[k] for k in (400, 401, 403)},
        },
    ),
)
class WorkshopProductListCreateView(OwnedByWorkshopMixin, generics.ListCreateAPIView):
    permission_classes = WORKSHOP_PERMISSIONS
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def get_queryset(self):
        return super().get_queryset().order_by("name", "id_product")

    def create(self, request, *args, **kwargs):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = create_product(request.user.id, serializer.validated_data)
        product.refresh_from_db()
        return Response(
            ProductSerializer(product, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    patch=extend_schema(
        summary="Edita/desativa produto (multipart parcial; sem DELETE)",
        request={
            "multipart/form-data": ProductWriteSerializer,
            "application/json": ProductWriteSerializer,
        },
        responses={
            200: ProductSerializer,
            **{k: ERROR_RESPONSES[k] for k in (400, 401, 403, 404)},
        },
    )
)
class WorkshopProductDetailView(OwnedByWorkshopMixin, generics.GenericAPIView):
    permission_classes = WORKSHOP_PERMISSIONS
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def patch(self, request, *args, **kwargs):
        product = self.get_object()
        serializer = ProductWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = update_product(product, serializer.validated_data)
        product.refresh_from_db()
        return Response(
            ProductSerializer(product, context=self.get_serializer_context()).data
        )


# ------------------------------------------------- produtos públicos (BE-066)


@extend_schema_view(
    get=extend_schema(
        summary="Catálogo informativo de produtos da oficina (público)",
        description="Só produtos `active` (indisponíveis aparecem com `disponibility=false`). "
        "Oficina não pública → 404.",
        responses={200: PublicProductSerializer(many=True), 404: ERROR_RESPONSES[404]},
    )
)
class PublicWorkshopProductListView(PublicCacheMixin, generics.ListAPIView):
    cache_max_age = 60
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicProductSerializer
    queryset = Product.objects.none()

    def get_queryset(self):
        from apps.core.mixins import is_schema_generation
        from apps.workshops.selectors import public_workshop_or_404

        if is_schema_generation(self):
            return self.queryset
        workshop = public_workshop_or_404(self.kwargs["workshop_id"])
        return Product.objects.filter(workshop_id=workshop.pk, active=True).order_by(
            "name", "id_product"
        )
