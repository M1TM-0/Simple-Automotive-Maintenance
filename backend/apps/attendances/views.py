"""Atendimentos e orçamentos: cliente (BE-045…BE-048) e oficina (BE-049…BE-055).

Recurso de outro dono → 404 (querysets filtrados pela sessão); perfil errado → 403.
"""

from apps.attendances.filters import ClientAttendanceFilter, WorkshopAttendanceFilter
from apps.attendances.models import Attendance, Budget, BudgetItem
from apps.attendances.selectors import (
    attendance_detail,
    attendance_list,
    workshop_client_vehicles,
    workshop_clients,
)
from apps.attendances.serializers import (
    AttendanceCreateSerializer,
    BudgetActionSerializer,
    BudgetItemResponseSerializer,
    BudgetItemSerializer,
    BudgetItemWriteSerializer,
    BudgetSerializer,
    BudgetWriteSerializer,
    ClientAttendanceDetailSerializer,
    ClientAttendanceSerializer,
    ExecutionSerializer,
    TransitionSerializer,
    WorkshopAttendanceDetailSerializer,
    WorkshopAttendanceSerializer,
    WorkshopAttendanceUpdateSerializer,
    WorkshopClientSerializer,
    WorkshopClientVehicleSerializer,
)
from apps.attendances.services import (
    add_budget_item,
    cancel_attendance,
    create_budget,
    remove_budget_item,
    request_attendance,
    respond_budget,
    send_budget,
    set_item_execution,
    transition_attendance,
    update_attendance,
    update_budget,
    update_budget_item,
)
from apps.core.mixins import is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.core.permissions import WORKSHOP_PERMISSIONS, IsClient
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

STATUS_PARAM = OpenApiParameter(
    "status",
    OpenApiTypes.STR,
    description="Lista separada por vírgula: `requested,budgeted`.",
)


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


def _client_id(view):
    return view.request.user.id


# =================================================================== cliente


@extend_schema_view(
    get=extend_schema(
        summary="Atendimentos do cliente",
        parameters=[STATUS_PARAM, OpenApiParameter("vehicle", OpenApiTypes.INT)],
    ),
    post=extend_schema(
        summary="Solicita atendimento a uma oficina",
        request=AttendanceCreateSerializer,
        responses={201: ClientAttendanceDetailSerializer, **_errors(400, 401, 403)},
    ),
)
class ClientAttendanceListCreateView(generics.ListCreateAPIView):
    """BE-045 e BE-046."""

    permission_classes = [IsClient]
    serializer_class = ClientAttendanceSerializer
    filterset_class = ClientAttendanceFilter
    queryset = Attendance.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return attendance_list(client_id=_client_id(self))

    def create(self, request, *args, **kwargs):
        serializer = AttendanceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance = request_attendance(request.user.id, serializer.validated_data)
        instance = attendance_detail(pk=attendance.pk).get()
        return Response(
            ClientAttendanceDetailSerializer(
                instance, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )


class _ClientAttendanceObject(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientAttendanceDetailSerializer
    queryset = Attendance.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return attendance_detail(client_id=_client_id(self))

    def detail_response(self, pk):
        instance = self.get_queryset().get(pk=pk)
        return Response(
            ClientAttendanceDetailSerializer(
                instance, context=self.get_serializer_context()
            ).data
        )


@extend_schema_view(
    get=extend_schema(
        summary="Detalhe: oficina, veículo, orçamentos (itens) e avaliação"
    )
)
class ClientAttendanceDetailView(_ClientAttendanceObject, generics.RetrieveAPIView):
    """BE-046."""


class ClientAttendanceCancelView(_ClientAttendanceObject):
    """BE-047: cancela (a trigger cancela os orçamentos); estado final → 409."""

    @extend_schema(
        summary="Cliente cancela o atendimento",
        request=None,
        responses={
            200: ClientAttendanceDetailSerializer,
            **_errors(401, 403, 404, 409),
        },
    )
    def post(self, request, pk):
        attendance = self.get_object()
        cancel_attendance(attendance)
        return self.detail_response(attendance.pk)


class _ClientBudgetAction(APIView):
    permission_classes = [IsClient]
    approve = None

    @extend_schema(
        request=None,
        responses={200: BudgetActionSerializer, **_errors(401, 403, 404, 409)},
    )
    def post(self, request, pk):
        budget = get_object_or_404(Budget, pk=pk, attendance__client_id=request.user.id)
        budget = respond_budget(budget, approve=self.approve)
        budget = (
            Budget.objects.select_related("attendance")
            .prefetch_related("items")
            .get(pk=budget.pk)
        )
        return Response(BudgetActionSerializer(budget).data)


class ClientBudgetApproveView(_ClientBudgetAction):
    """BE-048: aprova (o banco exige `waiting_approval`, validade e itens)."""

    approve = True


class ClientBudgetRejectView(_ClientBudgetAction):
    """BE-048: recusa (o atendimento volta a `requested`)."""

    approve = False


# =================================================================== oficina


class _WorkshopScoped(generics.GenericAPIView):
    permission_classes = WORKSHOP_PERMISSIONS
    queryset = Attendance.objects.none()

    @property
    def workshop_id(self):
        return self.request.user.id

    def attendance_or_404(self, pk):
        return get_object_or_404(Attendance, pk=pk, workshop_id=self.workshop_id)

    def budget_or_404(self, pk):
        return get_object_or_404(Budget, pk=pk, workshop_id=self.workshop_id)

    def item_or_404(self, budget_pk, item_pk):
        return get_object_or_404(
            BudgetItem, pk=item_pk, budget_id=budget_pk, workshop_id=self.workshop_id
        )

    def detail_response(self, pk, status_code=status.HTTP_200_OK):
        instance = attendance_detail(pk=pk, workshop_id=self.workshop_id).get()
        data = WorkshopAttendanceDetailSerializer(
            instance, context=self.get_serializer_context()
        ).data
        return Response(data, status=status_code)


@extend_schema_view(
    get=extend_schema(
        summary="Atendimentos da oficina (quadro/lista)", parameters=[STATUS_PARAM]
    )
)
class WorkshopAttendanceListView(_WorkshopScoped, generics.ListAPIView):
    """BE-049."""

    serializer_class = WorkshopAttendanceSerializer
    filterset_class = WorkshopAttendanceFilter

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return attendance_list(workshop_id=self.workshop_id)


class WorkshopAttendanceDetailView(_WorkshopScoped):
    """BE-049: detalhe e atualização de km/observações técnicas (status ignorado)."""

    serializer_class = WorkshopAttendanceDetailSerializer

    @extend_schema(
        summary="Detalhe do atendimento",
        responses={200: WorkshopAttendanceDetailSerializer, **_errors(401, 403, 404)},
    )
    def get(self, request, pk):
        self.attendance_or_404(pk)
        return self.detail_response(pk)

    @extend_schema(
        summary="Atualiza quilometragem e observações técnicas",
        request=WorkshopAttendanceUpdateSerializer,
        responses={
            200: WorkshopAttendanceDetailSerializer,
            **_errors(400, 401, 403, 404, 409),
        },
    )
    def patch(self, request, pk):
        attendance = self.attendance_or_404(pk)
        serializer = WorkshopAttendanceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_attendance(attendance, serializer.validated_data)
        return self.detail_response(pk)


class WorkshopAttendanceTransitionView(_WorkshopScoped):
    """BE-050."""

    serializer_class = WorkshopAttendanceDetailSerializer

    @extend_schema(
        summary="Transição de status feita pela oficina",
        request=TransitionSerializer,
        responses={
            200: WorkshopAttendanceDetailSerializer,
            **_errors(400, 401, 403, 404, 409),
        },
    )
    def post(self, request, pk):
        attendance = self.attendance_or_404(pk)
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transition_attendance(attendance, serializer.validated_data["status"])
        return self.detail_response(pk)


class WorkshopBudgetCreateView(_WorkshopScoped):
    """BE-051: cria o orçamento pendente (atendimento → `budgeted`)."""

    serializer_class = BudgetSerializer

    @extend_schema(
        summary="Cria orçamento pendente",
        request=BudgetWriteSerializer,
        responses={201: BudgetSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def post(self, request, pk):
        attendance = self.attendance_or_404(pk)
        serializer = BudgetWriteSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        budget = create_budget(attendance, serializer.validated_data)
        return Response(BudgetSerializer(budget).data, status=status.HTTP_201_CREATED)


class WorkshopBudgetDetailView(_WorkshopScoped):
    """BE-051: validade e observações do orçamento em edição."""

    serializer_class = BudgetSerializer

    @extend_schema(
        summary="Edita validade e observações do orçamento pendente",
        request=BudgetWriteSerializer,
        responses={200: BudgetSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def patch(self, request, id_budget):
        budget = self.budget_or_404(id_budget)
        serializer = BudgetWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        budget = update_budget(budget, serializer.validated_data)
        return Response(BudgetSerializer(budget).data)


def _item_response(item, status_code=status.HTTP_200_OK):
    item = BudgetItem.objects.select_related("budget").get(pk=item.pk)
    return Response(BudgetItemResponseSerializer(item).data, status=status_code)


class WorkshopBudgetItemCreateView(_WorkshopScoped):
    """BE-052: inclui item (resposta com o `total_price` recalculado)."""

    serializer_class = BudgetItemResponseSerializer

    @extend_schema(
        summary="Inclui item (serviço, produto, mão de obra, outro)",
        request=BudgetItemWriteSerializer,
        responses={
            201: BudgetItemResponseSerializer,
            **_errors(400, 401, 403, 404, 409),
        },
    )
    def post(self, request, id_budget):
        budget = self.budget_or_404(id_budget)
        serializer = BudgetItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = add_budget_item(budget, serializer.validated_data)
        return _item_response(item, status.HTTP_201_CREATED)


class WorkshopBudgetItemDetailView(_WorkshopScoped):
    """BE-052: edita ou remove item (somente orçamento em edição)."""

    serializer_class = BudgetItemResponseSerializer

    @extend_schema(
        summary="Edita item",
        request=BudgetItemWriteSerializer,
        responses={
            200: BudgetItemResponseSerializer,
            **_errors(400, 401, 403, 404, 409),
        },
    )
    def patch(self, request, id_budget, id_budget_item):
        item = self.item_or_404(id_budget, id_budget_item)
        serializer = BudgetItemWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = update_budget_item(item, serializer.validated_data)
        return _item_response(item)

    @extend_schema(
        summary="Remove item (um serviço leva junto as peças ligadas a ele)",
        responses={204: None, **_errors(401, 403, 404, 409)},
    )
    def delete(self, request, id_budget, id_budget_item):
        remove_budget_item(self.item_or_404(id_budget, id_budget_item))
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkshopBudgetSendView(_WorkshopScoped):
    """BE-053."""

    serializer_class = BudgetActionSerializer

    @extend_schema(
        summary="Envia orçamento ao cliente (budgeted → waiting_approval)",
        request=None,
        responses={200: BudgetActionSerializer, **_errors(401, 403, 404, 409)},
    )
    def post(self, request, id_budget):
        budget = send_budget(self.budget_or_404(id_budget))
        budget = (
            Budget.objects.select_related("attendance")
            .prefetch_related("items")
            .get(pk=budget.pk)
        )
        return Response(BudgetActionSerializer(budget).data)


class WorkshopBudgetItemExecutionView(_WorkshopScoped):
    """BE-054."""

    serializer_class = BudgetItemSerializer

    @extend_schema(
        summary="Marca item executado / não executado / pendente (atendimento in_progress)",
        request=ExecutionSerializer,
        responses={200: BudgetItemSerializer, **_errors(400, 401, 403, 404, 409)},
    )
    def patch(self, request, id_budget, id_budget_item):
        item = self.item_or_404(id_budget, id_budget_item)
        serializer = ExecutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = set_item_execution(item, serializer.validated_data["execution_status"])
        return Response(BudgetItemSerializer(item).data)


@extend_schema_view(get=extend_schema(summary="Clientes atendidos pela oficina"))
class WorkshopClientListView(_WorkshopScoped, generics.ListAPIView):
    """BE-055."""

    serializer_class = WorkshopClientSerializer

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return workshop_clients(self.workshop_id)


@extend_schema_view(
    get=extend_schema(
        summary="Veículos do cliente atendidos pela oficina + atendimentos",
        responses={
            200: WorkshopClientVehicleSerializer(many=True),
            **_errors(401, 403, 404),
        },
    )
)
class WorkshopClientVehiclesView(_WorkshopScoped, generics.ListAPIView):
    """BE-055: cliente sem atendimento nesta oficina → 404."""

    serializer_class = WorkshopClientVehicleSerializer

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        if not Attendance.objects.filter(
            workshop_id=self.workshop_id, client_id=self.kwargs["id_client"]
        ).exists():
            raise NotFound("Cliente não encontrado.")
        return workshop_client_vehicles(self.workshop_id, self.kwargs["id_client"])
