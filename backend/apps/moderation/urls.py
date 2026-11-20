# Rotas `/api/admin/*` (BE-073, BE-074), montadas em `api/admin/` no config/urls.py.
# Toda view daqui herda de `apps.moderation.views.AdminViewMixin` (permissão is_staff +
# auditoria, BE-035); `apps/moderation/tests/test_admin_access.py` confere isso.
from apps.moderation.views import (
    AdminDenunciationDetailView,
    AdminDenunciationListView,
    AdminReviewHideView,
    AdminServiceRequestApproveView,
    AdminServiceRequestListView,
    AdminServiceRequestRejectView,
)
from django.urls import path

urlpatterns = [
    path(
        "denunciations/",
        AdminDenunciationListView.as_view(),
        name="admin-denunciations",
    ),
    path(
        "denunciations/<int:id>/",
        AdminDenunciationDetailView.as_view(),
        name="admin-denunciation",
    ),
    path(
        "reviews/<uuid:pk>/hide/",
        AdminReviewHideView.as_view(),
        name="admin-review-hide",
    ),
    path(
        "service-requests/",
        AdminServiceRequestListView.as_view(),
        name="admin-service-requests",
    ),
    path(
        "service-requests/<int:pk>/approve/",
        AdminServiceRequestApproveView.as_view(),
        name="admin-service-request-approve",
    ),
    path(
        "service-requests/<int:pk>/reject/",
        AdminServiceRequestRejectView.as_view(),
        name="admin-service-request-reject",
    ),
]
