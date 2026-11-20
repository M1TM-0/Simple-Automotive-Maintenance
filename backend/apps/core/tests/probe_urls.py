"""URLconf de teste: as rotas do projeto + views-sonda sob `/api/_probe/`.

As sondas exercitam os mixins de dono e as permissões de forma genérica (BE-030),
inclusive o `owner_lookup` aninhado. As rotas reais têm testes próprios em cada app
(a base admin de BE-035 é testada pelas rotas reais de BE-073/BE-074).
Use com `@pytest.mark.urls("apps.core.tests.probe_urls")`.
"""

from apps.catalog.models import Product
from apps.chat.models import Chat
from apps.core.mixins import OwnedByClientMixin, OwnedByWorkshopMixin
from apps.core.permissions import WORKSHOP_PERMISSIONS, IsChatParticipant, IsClient
from apps.vehicles.models import RegisterMaintenance, Vehicle
from config.urls import handler400, handler403, handler404, handler500  # noqa: F401
from config.urls import urlpatterns as project_urlpatterns
from django.urls import path
from rest_framework import generics, serializers


class VehicleProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id_vehicle", "plate"]


class ProductProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id_product", "name"]


class ChatProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["id_chat"]


class MaintenanceProbeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegisterMaintenance
        fields = ["id_register_maintenance"]


class ClientVehicleList(OwnedByClientMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    queryset = Vehicle.objects.order_by("id_vehicle")
    serializer_class = VehicleProbeSerializer


class ClientVehicleDetail(OwnedByClientMixin, generics.RetrieveAPIView):
    permission_classes = [IsClient]
    queryset = Vehicle.objects.all()
    serializer_class = VehicleProbeSerializer


class ClientMaintenanceList(OwnedByClientMixin, generics.ListAPIView):
    """Dono aninhado: histórico → veículo → cliente."""

    permission_classes = [IsClient]
    owner_lookup = "vehicle__client_id"
    queryset = RegisterMaintenance.objects.order_by("id_register_maintenance")
    serializer_class = MaintenanceProbeSerializer


class WorkshopProductDetail(OwnedByWorkshopMixin, generics.RetrieveAPIView):
    permission_classes = WORKSHOP_PERMISSIONS
    queryset = Product.objects.all()
    serializer_class = ProductProbeSerializer


class ChatDetail(generics.RetrieveAPIView):
    permission_classes = [IsChatParticipant]
    queryset = Chat.objects.all()
    serializer_class = ChatProbeSerializer


urlpatterns = [
    path("api/_probe/vehicles/", ClientVehicleList.as_view()),
    path("api/_probe/vehicles/<int:pk>/", ClientVehicleDetail.as_view()),
    path("api/_probe/maintenance/", ClientMaintenanceList.as_view()),
    path("api/_probe/workshop/products/<int:pk>/", WorkshopProductDetail.as_view()),
    path("api/_probe/chats/<int:pk>/", ChatDetail.as_view()),
    *project_urlpatterns,
]
