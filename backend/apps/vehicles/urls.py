from apps.vehicles.views import (
    VehicleDetailView,
    VehicleHistoryRecordView,
    VehicleHistoryView,
    VehicleListCreateView,
    VehicleUpcomingMaintenanceView,
    WorkshopVehicleHistoryView,
)
from django.urls import path

urlpatterns = [
    path("vehicles/", VehicleListCreateView.as_view(), name="vehicles"),
    path("vehicles/<int:pk>/", VehicleDetailView.as_view(), name="vehicle-detail"),
    path(
        "vehicles/<int:id_vehicle>/history/",
        VehicleHistoryView.as_view(),
        name="vehicle-history",
    ),
    path(
        "vehicles/<int:id_vehicle>/history/<str:record>/",
        VehicleHistoryRecordView.as_view(),
        name="vehicle-history-record",
    ),
    path(
        "vehicles/<int:id_vehicle>/upcoming-maintenance/",
        VehicleUpcomingMaintenanceView.as_view(),
        name="vehicle-upcoming-maintenance",
    ),
    path(
        "workshop/vehicles/<int:id_vehicle>/history/",
        WorkshopVehicleHistoryView.as_view(),
        name="workshop-vehicle-history",
    ),
]
