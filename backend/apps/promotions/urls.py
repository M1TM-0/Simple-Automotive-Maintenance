from apps.promotions.views import (
    PublicPromotionListView,
    PublicWorkshopPromotionListView,
    WorkshopAdvertisementListCreateView,
    WorkshopPromotionDetailView,
    WorkshopPromotionListCreateView,
)
from django.urls import path

urlpatterns = [
    path(
        "workshop/promotions/",
        WorkshopPromotionListCreateView.as_view(),
        name="workshop-promotions",
    ),
    path(
        "workshop/promotions/<int:pk>/",
        WorkshopPromotionDetailView.as_view(),
        name="workshop-promotion-detail",
    ),
    path(
        "workshop/promotions/<int:pk>/advertisements/",
        WorkshopAdvertisementListCreateView.as_view(),
        name="workshop-promotion-advertisements",
    ),
    # Públicas (BE-066, BE-068)
    path("promotions/", PublicPromotionListView.as_view(), name="public-promotions"),
    path(
        "workshops/<int:workshop_id>/promotions/",
        PublicWorkshopPromotionListView.as_view(),
        name="public-workshop-promotions",
    ),
]
