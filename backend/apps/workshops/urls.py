from apps.workshops.views import (
    ExternalMapPointsView,
    MapPointsView,
    OperationHoursView,
    PointsOfInterestView,
    PublicWorkshopView,
    WorkshopMeView,
    WorkshopPageView,
    WorkshopPointView,
)
from django.urls import path

urlpatterns = [
    path("workshop/me/", WorkshopMeView.as_view(), name="workshop-me"),
    path("workshop/page/", WorkshopPageView.as_view(), name="workshop-page"),
    path(
        "workshop/operation-hours/",
        OperationHoursView.as_view(),
        name="workshop-operation-hours",
    ),
    path("workshop/point/", WorkshopPointView.as_view(), name="workshop-point"),
    path(
        "points-of-interest/", PointsOfInterestView.as_view(), name="points-of-interest"
    ),
    # Públicas (BE-065, BE-067)
    path("workshops/<int:pk>/", PublicWorkshopView.as_view(), name="public-workshop"),
    path("map/points/", MapPointsView.as_view(), name="map-points"),
    # Segunda fonte do mapa: OpenStreetMap pela Overpass (BE-094, ADR 0010)
    path(
        "map/external-points/",
        ExternalMapPointsView.as_view(),
        name="map-external-points",
    ),
]
