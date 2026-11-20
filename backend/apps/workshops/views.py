"""Oficina: assistente T17 / perfil T21 (BE-037…BE-040) e leituras públicas (BE-065, BE-067).

As rotas `/workshop/*` daqui são do assistente: exigem o perfil oficina, mas não o
cadastro concluído (`WORKSHOP_WIZARD_PERMISSIONS`). `/workshops/{id}/` e
`/map/points/` são públicas (`AllowAny`) e só mostram oficinas públicas (DP-20).
"""

from apps.accounts.models import Workshop
from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES, paginated
from apps.core.pagination import SamPagination
from apps.core.permissions import WORKSHOP_WIZARD_PERMISSIONS
from apps.core.search import search_filter
from apps.core.throttles import ExternalMapRateThrottle
from apps.workshops import overpass
from apps.workshops.models import OperationHour, PagWorkshop, PointOfInterest
from apps.workshops.selectors import (
    category_ids_for,
    map_points,
    sam_points_for_dedup,
    workshop_profile,
)
from apps.workshops.serializers import (
    ExternalPointsQuerySerializer,
    ExternalPointsResponseSerializer,
    MapPointSerializer,
    MapQuerySerializer,
    OperationHourInputSerializer,
    OperationHourSerializer,
    PageSerializer,
    PageUpdateSerializer,
    PointLinkSerializer,
    PointOfInterestSearchSerializer,
    PointSerializer,
    PublicWorkshopSerializer,
    WorkshopMeSerializer,
    WorkshopMeUpdateSerializer,
)
from apps.workshops.services import (
    link_point,
    replace_operation_hours,
    update_workshop_account,
    update_workshop_page,
)
from django.db.models import OuterRef, Subquery
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


def _first_item_error(errors):
    """Erros de lista do DRF (dict por índice ou lista) → `{campo: ["Horário N: msg"]}`."""
    items = (
        sorted(errors.items()) if isinstance(errors, dict) else list(enumerate(errors))
    )
    for index, item_errors in items:
        if not item_errors:
            continue
        if not isinstance(item_errors, dict):
            return {"detail": f"Horário {int(index) + 1}: {item_errors[0]}"}
        field, messages = next(iter(item_errors.items()))
        return {field: [f"Horário {int(index) + 1}: {messages[0]}"]}
    return {"detail": "Lista de horários inválida."}


class WorkshopMeView(APIView):
    """BE-037: dados da oficina logada com `point`, `page` e `setup_complete`."""

    permission_classes = WORKSHOP_WIZARD_PERMISSIONS

    def _payload(self, request):
        workshop = Workshop.objects.select_related("page", "point_of_interest").get(
            pk=request.user.id
        )
        return WorkshopMeSerializer(workshop, context={"request": request}).data

    @extend_schema(
        summary="Dados da oficina logada",
        responses={200: WorkshopMeSerializer, **_errors(401, 403)},
    )
    def get(self, request):
        return Response(self._payload(request))

    @extend_schema(
        summary="Edita nome fantasia, responsável e telefone (cnpj/email somente leitura)",
        request=WorkshopMeUpdateSerializer,
        responses={200: WorkshopMeSerializer, **_errors(400, 401, 403)},
    )
    def patch(self, request):
        serializer = WorkshopMeUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_workshop_account(request.user.id, serializer.validated_data)
        return Response(self._payload(request))


class WorkshopPageView(APIView):
    """BE-038: vitrine pública (descrição, foto de perfil e banner)."""

    permission_classes = WORKSHOP_WIZARD_PERMISSIONS

    @extend_schema(
        summary='Edita descrição, foto de perfil e banner (multipart; "" remove)',
        request={
            "multipart/form-data": PageUpdateSerializer,
            "application/json": PageUpdateSerializer,
        },
        responses={200: PageSerializer, **_errors(400, 401, 403)},
    )
    def patch(self, request):
        serializer = PageUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_workshop_page(request.user.id, serializer.validated_data)
        page = PagWorkshop.objects.get(workshop_id=request.user.id)
        return Response(PageSerializer(page, context={"request": request}).data)


HOURS_PAGE = paginated(OperationHourSerializer, "PaginatedOperationHourList")


class OperationHoursView(APIView):
    """BE-039: lista e substitui (PUT atômico) os horários de funcionamento."""

    permission_classes = WORKSHOP_WIZARD_PERMISSIONS

    def _list(self, request):
        queryset = OperationHour.objects.filter(workshop_id=request.user.id).order_by(
            "day_of_week", "opening_time", "id_operation_hour"
        )
        paginator = SamPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            OperationHourSerializer(page, many=True).data
        )

    @extend_schema(
        summary="Horários de funcionamento (1 = segunda … 7 = domingo)",
        responses={200: HOURS_PAGE, **_errors(401, 403)},
    )
    def get(self, request):
        return self._list(request)

    @extend_schema(
        summary="Substitui a lista de horários (atômico)",
        description=(
            "Corpo: lista `[{day_of_week, opening_time, closing_time}]`. Vários intervalos "
            "por dia são aceitos desde que não se sobreponham (08–12 e 12–18 valem). "
            "`[]` deixa a oficina sem horários (fechada). Erro → 400 e nada muda."
        ),
        request=OperationHourInputSerializer(many=True),
        responses={200: HOURS_PAGE, **_errors(400, 401, 403)},
    )
    def put(self, request):
        if not isinstance(request.data, list):
            raise ValidationError(
                {"detail": "Envie a lista de horários (um array JSON)."}
            )
        serializer = OperationHourInputSerializer(data=request.data, many=True)
        if not serializer.is_valid():
            raise ValidationError(_first_item_error(serializer.errors))
        replace_operation_hours(request.user.id, serializer.validated_data)
        return self._list(request)


@extend_schema_view(
    get=extend_schema(
        summary="Busca pontos do mapa para a oficina escolher o seu",
        description="`q` busca no nome e no endereço (texto normalizado, sem acentos). "
        "`claimed` = já vinculado a outra oficina.",
        parameters=[OpenApiParameter("q", OpenApiTypes.STR)],
    )
)
class PointsOfInterestView(generics.ListAPIView):
    """BE-040: `GET /points-of-interest/?q=`."""

    permission_classes = WORKSHOP_WIZARD_PERMISSIONS
    serializer_class = PointOfInterestSearchSerializer
    queryset = PointOfInterest.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        owner = Workshop.objects.filter(point_of_interest=OuterRef("pk")).values("pk")[
            :1
        ]
        queryset = PointOfInterest.objects.annotate(owner_id=Subquery(owner))
        queryset = search_filter(
            queryset, self.request.query_params.get("q"), "name", "address"
        )
        return queryset.order_by("name", "id_point_of_interest")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["workshop_id"] = getattr(self.request.user, "id", None)
        return context


class WorkshopPointView(APIView):
    """BE-040: `POST /workshop/point/`."""

    permission_classes = WORKSHOP_WIZARD_PERMISSIONS

    @extend_schema(
        summary="Vincula POI existente ou cria ponto novo e vincula",
        request=PointLinkSerializer,
        responses={200: PointSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request):
        serializer = PointLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        point = link_point(request.user.id, serializer.validated_data)
        return Response(PointSerializer(point).data)


# ------------------------------------------------------------- público (Fase 4)


class PublicWorkshopView(APIView):
    """BE-065: `GET /workshops/{id}/` — perfil público completo numa resposta."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Perfil público da oficina",
        description=(
            "Público (sem login). Oficina inexistente, inativa, bloqueada ou com cadastro "
            "não concluído → 404 (DP-20). `is_favorite` só com sessão de cliente; "
            "`is_open_now` pelos horários no fuso do negócio (DP-16), `null` sem horários. "
            "Não expõe CNPJ, e-mail nem responsável."
        ),
        responses={200: PublicWorkshopSerializer, 404: ERROR_RESPONSES[404]},
    )
    def get(self, request, pk):
        user = request.user
        client_id = user.id if getattr(user, "role", None) == "client" else None
        workshop = workshop_profile(pk, client_id=client_id)
        if workshop is None:
            raise NotFound("Oficina não encontrada.")
        return Response(
            PublicWorkshopSerializer(workshop, context={"request": request}).data
        )


class MapPagination(SamPagination):
    """O mapa lê só a 1ª página: 100 pontos por padrão (até 200 com `page_size`)."""

    page_size = 100
    max_page_size = 200


@extend_schema_view(
    get=extend_schema(
        summary="Pontos do mapa: oficinas cadastradas e pontos de interesse",
        description=(
            "Público. `kind=workshop` (oficina pública com ponto) ou `kind=poi` (ponto sem "
            "oficina vinculada; um ponto vinculado aparece só como oficina). "
            "`q` busca no nome (e, nas oficinas, no nome dos serviços) sem acentos; "
            "`category` (id ou nome) e `open_now=true` retornam só oficinas; "
            "`lat`/`lng` calculam `distance_km` e ordenam por proximidade dentro de "
            "`radius_km` (padrão 10, máximo 100 → acima disso 400)."
        ),
        parameters=[MapQuerySerializer],
        responses={200: MapPointSerializer(many=True), 400: ERROR_RESPONSES[400]},
    )
)
class MapPointsView(generics.ListAPIView):
    """BE-067: `GET /map/points/`."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = MapPointSerializer
    pagination_class = MapPagination
    queryset = PointOfInterest.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        params = MapQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        filters = dict(params.validated_data)
        category = (filters.pop("category", "") or "").strip()
        filters["category_ids"] = category_ids_for(category) if category else None
        return map_points(filters)


@extend_schema_view(
    get=extend_schema(
        summary="Estabelecimentos do OpenStreetMap na região visível (não cadastrados)",
        description=(
            "Público. Postos de combustível, borracharias, oficinas, autopeças, lava-jatos "
            "e reparos do OpenStreetMap (Overpass API) dentro da caixa `south`/`west`/"
            "`north`/`east`, **sem** o que já está no SAM (mesmo id do OSM, mesmo lugar ou "
            "nome parecido a até 100 m). Só exibição: sem perfil, chat, favorito ou "
            "atendimento. Responde **200 mesmo com a Overpass fora do ar** (`status`): as "
            "oficinas do SAM vêm de `/map/points/` e não dependem daqui. Região acima de "
            "16 células de 0,05° → `too_large` sem consulta. Dados © OpenStreetMap "
            "contributors (ODbL)."
        ),
        parameters=[ExternalPointsQuerySerializer],
        responses={
            200: ExternalPointsResponseSerializer,
            400: ERROR_RESPONSES[400],
            429: ERROR_RESPONSES[429],
        },
    )
)
class ExternalMapPointsView(APIView):
    """BE-094: `GET /map/external-points/` — segunda fonte do mapa (ADR 0010)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ExternalMapRateThrottle]

    def get(self, request):
        params = ExternalPointsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        box = params.validated_data
        south, west, north, east = box["south"], box["west"], box["north"], box["east"]

        found = overpass.external_points(south, west, north, east)
        results = found.results
        if results:
            results = overpass.drop_sam_duplicates(
                results, sam_points_for_dedup(south, west, north, east)
            )
        payload = {
            "status": found.status,
            "detail": found.detail,
            "source": overpass.SOURCE,
            "attribution": overpass.ATTRIBUTION,
            "license": overpass.LICENSE,
            "license_url": overpass.LICENSE_URL,
            "count": len(results),
            "results": results,
        }
        response = Response(ExternalPointsResponseSerializer(payload).data)
        # Região completa pode ficar 5 min no navegador; falha não (tenta de novo depois).
        response["Cache-Control"] = (
            "public, max-age=300" if found.status == overpass.STATUS_OK else "no-store"
        )
        return response
