"""Veículos do cliente, histórico e histórico autorizado para a oficina."""

from apps.attendances.models import Attendance
from apps.core.mixins import OwnedByClientMixin, is_schema_generation
from apps.core.openapi import ERROR_RESPONSES
from apps.core.permissions import WORKSHOP_PERMISSIONS, IsClient
from apps.vehicles.models import Vehicle, VehicleMaintenanceHistory
from apps.vehicles.reminders import reminders_sent, vehicle_upcoming
from apps.vehicles.selectors import vehicle_history
from apps.vehicles.serializers import (
    MaintenanceHistorySerializer,
    ManualMaintenanceSerializer,
    UpcomingMaintenanceSerializer,
    VehicleSerializer,
    VehicleWriteSerializer,
)
from apps.vehicles.services import (
    add_manual_history,
    create_vehicle,
    delete_vehicle,
    update_vehicle,
)
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

# A view do histórico tem PK composta: os parâmetros de rota são declarados à mão.
VEHICLE_PK = OpenApiParameter(
    "id_vehicle", OpenApiTypes.INT, OpenApiParameter.PATH, description="Id do veículo."
)
RECORD_ID = OpenApiParameter(
    "record",
    OpenApiTypes.STR,
    OpenApiParameter.PATH,
    description="`<record_type>-<id_record>`.",
)
HISTORY_NOT_SHARED = "O cliente não autorizou a consulta do histórico deste veículo."
WRITE_BODY = {
    "multipart/form-data": VehicleWriteSerializer,
    "application/json": VehicleWriteSerializer,
}


def _errors(*codes):
    return {code: ERROR_RESPONSES[code] for code in codes}


class _ClientVehicles(OwnedByClientMixin):
    permission_classes = [IsClient]
    queryset = Vehicle.objects.all()


@extend_schema_view(
    get=extend_schema(summary="Veículos do cliente"),
    post=extend_schema(
        summary="Cadastra veículo (multipart, até 3 fotos)",
        request=WRITE_BODY,
        responses={201: VehicleSerializer, **_errors(400, 401, 403)},
    ),
)
class VehicleListCreateView(_ClientVehicles, generics.ListCreateAPIView):
    """BE-043."""

    serializer_class = VehicleSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("brand", "model", "id_vehicle")

    def create(self, request, *args, **kwargs):
        serializer = VehicleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = create_vehicle(request.user.id, serializer.validated_data)
        vehicle.refresh_from_db()
        return Response(
            VehicleSerializer(vehicle, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(
        summary="Detalha veículo próprio",
        responses={200: VehicleSerializer, **_errors(401, 403, 404)},
    ),
    patch=extend_schema(
        summary='Edita veículo e/ou history_shared ("" limpa a foto da posição)',
        request=WRITE_BODY,
        responses={200: VehicleSerializer, **_errors(400, 401, 403, 404)},
    ),
    delete=extend_schema(
        summary="Exclui veículo sem atendimento nem histórico",
        responses={204: None, **_errors(401, 403, 404, 409)},
    ),
)
class VehicleDetailView(_ClientVehicles, generics.RetrieveAPIView):
    """BE-043. Outro cliente → 404 (queryset filtrado pelo dono)."""

    serializer_class = VehicleSerializer

    def patch(self, request, *args, **kwargs):
        vehicle = self.get_object()
        serializer = VehicleWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vehicle = update_vehicle(vehicle, serializer.validated_data)
        vehicle.refresh_from_db()
        return Response(
            VehicleSerializer(vehicle, context=self.get_serializer_context()).data
        )

    def delete(self, request, *args, **kwargs):
        delete_vehicle(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ histórico


@extend_schema_view(
    get=extend_schema(
        summary="Histórico (serviços e peças) do veículo, mais recente primeiro",
        parameters=[VEHICLE_PK],
    ),
    post=extend_schema(
        summary="Registro manual de manutenção (somente inclusão)",
        parameters=[VEHICLE_PK],
        request=ManualMaintenanceSerializer,
        responses={201: MaintenanceHistorySerializer, **_errors(400, 401, 403, 404)},
    ),
)
class VehicleHistoryView(generics.ListCreateAPIView):
    """BE-044. O histórico só cresce: não há PUT/PATCH/DELETE (405)."""

    permission_classes = [IsClient]
    serializer_class = MaintenanceHistorySerializer
    queryset = VehicleMaintenanceHistory.objects.none()

    def get_vehicle(self):
        return get_object_or_404(
            Vehicle, pk=self.kwargs["id_vehicle"], client_id=self.request.user.id
        )

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        return vehicle_history(self.get_vehicle().pk)

    def create(self, request, *args, **kwargs):
        vehicle = self.get_vehicle()
        serializer = ManualMaintenanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = add_manual_history(vehicle, serializer.validated_data)
        row = vehicle_history(vehicle.pk).get(
            record_type="service", id_record=record.pk
        )
        return Response(
            MaintenanceHistorySerializer(row).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    get=extend_schema(
        summary="Um registro do histórico (id = `<record_type>-<id_record>`)",
        parameters=[VEHICLE_PK, RECORD_ID],
    )
)
class VehicleHistoryRecordView(generics.RetrieveAPIView):
    """Registro individual: existe para que PATCH/PUT/DELETE respondam 405 (RN05)."""

    permission_classes = [IsClient]
    serializer_class = MaintenanceHistorySerializer
    queryset = VehicleMaintenanceHistory.objects.none()

    def get_object(self):
        vehicle = get_object_or_404(
            Vehicle, pk=self.kwargs["id_vehicle"], client_id=self.request.user.id
        )
        record_type, _, record_id = self.kwargs["record"].partition("-")
        if record_type not in ("service", "part") or not record_id.isdigit():
            raise NotFound("Registro não encontrado.")
        return get_object_or_404(
            vehicle_history(vehicle.pk),
            record_type=record_type,
            id_record=int(record_id),
        )


@extend_schema_view(
    get=extend_schema(
        summary="Histórico do veículo para a oficina (se o cliente autorizou)",
        parameters=[VEHICLE_PK],
        description="Sem atendimento desta oficina com o veículo → 404. "
        "Com vínculo, mas `history_shared=false` → 403 com `detail`.",
        responses={
            200: MaintenanceHistorySerializer(many=True),
            **_errors(401, 403, 404),
        },
    )
)
class WorkshopVehicleHistoryView(generics.ListAPIView):
    """BE-056 (DP-07): autorização do cliente **e** vínculo por atendimento."""

    permission_classes = WORKSHOP_PERMISSIONS
    serializer_class = MaintenanceHistorySerializer
    queryset = VehicleMaintenanceHistory.objects.none()

    def get_queryset(self):
        if is_schema_generation(self):
            return self.queryset
        linked = Attendance.objects.filter(
            vehicle_id=OuterRef("pk"), workshop_id=self.request.user.id
        )
        vehicle = get_object_or_404(
            Vehicle.objects.filter(Exists(linked)), pk=self.kwargs["id_vehicle"]
        )
        if not vehicle.history_shared:
            raise PermissionDenied(HISTORY_NOT_SHARED)
        return vehicle_history(vehicle.pk)


@extend_schema_view(
    get=extend_schema(
        summary="Próximas manutenções do veículo (preventiva por km)",
        parameters=[
            OpenApiParameter(
                "id_vehicle",
                OpenApiTypes.INT,
                OpenApiParameter.PATH,
                description="Id do veículo.",
            )
        ],
        description="Um item por serviço com intervalo em km informado no histórico: última execução, "
        "próxima km, quanto falta e a situação (`ok`, `soon`, `overdue`). Mais urgente primeiro. "
        "Itens sem intervalo ou cuja última execução não tem km não aparecem.",
        responses={
            200: UpcomingMaintenanceSerializer(many=True),
            **_errors(401, 403, 404),
        },
    )
)
class VehicleUpcomingMaintenanceView(generics.ListAPIView):
    """BE-077: o cálculo é do backend; o frontend só apresenta (T12)."""

    permission_classes = [IsClient]
    serializer_class = UpcomingMaintenanceSerializer
    queryset = Vehicle.objects.none()

    def list(self, request, *args, **kwargs):
        vehicle = get_object_or_404(
            Vehicle, pk=self.kwargs["id_vehicle"], client_id=request.user.id
        )
        page = self.paginate_queryset(vehicle_upcoming(vehicle))
        context = {
            **self.get_serializer_context(),
            "reminders": reminders_sent(i.last_record_id for i in page),
        }
        return self.get_paginated_response(
            UpcomingMaintenanceSerializer(page, many=True, context=context).data
        )
