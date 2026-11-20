from apps.catalog.views import (
    PublicWorkshopProductListView,
    ServiceCategoryListView,
    ServiceListView,
    WorkshopProductDetailView,
    WorkshopProductListCreateView,
    WorkshopServiceDetailView,
    WorkshopServiceListCreateView,
)
from django.urls import path

urlpatterns = [
    # Catálogo global, público (BE-036)
    path(
        "service-categories/",
        ServiceCategoryListView.as_view(),
        name="service-categories",
    ),
    path("services/", ServiceListView.as_view(), name="services"),
    # Produtos da oficina no perfil público (BE-066)
    path(
        "workshops/<int:workshop_id>/products/",
        PublicWorkshopProductListView.as_view(),
        name="public-workshop-products",
    ),
    # Catálogo da oficina (BE-041, BE-042)
    path(
        "workshop/services/",
        WorkshopServiceListCreateView.as_view(),
        name="workshop-services",
    ),
    path(
        "workshop/services/<int:pk>/",
        WorkshopServiceDetailView.as_view(),
        name="workshop-service-detail",
    ),
    path(
        "workshop/products/",
        WorkshopProductListCreateView.as_view(),
        name="workshop-products",
    ),
    path(
        "workshop/products/<int:pk>/",
        WorkshopProductDetailView.as_view(),
        name="workshop-product-detail",
    ),
]
