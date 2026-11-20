"""
URL configuration for config project.
"""

from apps.core.views import api_root
from apps.core.views_health import health_jobs, health_live, health_ready
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAdminUser

handler400 = "apps.core.views.bad_request"
handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"

docs_access = {
    "authentication_classes": [SessionAuthentication],
    "permission_classes": [AllowAny] if settings.DEBUG else [IsAdminUser],
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api_root, name="api-root"),
    path("api/health/", health_live, name="health-live"),
    path("api/health/ready/", health_ready, name="health-ready"),
    path("api/health/jobs/", health_jobs, name="health-jobs"),  # BE-092
    path("api/schema/", SpectacularAPIView.as_view(**docs_access), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema", **docs_access),
        name="docs",
    ),
    # Rotas da API (contrato: backlog seção 8). Cada app declara os caminhos completos
    # a partir de /api/; rotas da oficina ficam sob `workshop/` em vários apps.
    path("api/", include("apps.accounts.urls")),  # auth/*, me/, favorites/
    path(
        "api/", include("apps.catalog.urls")
    ),  # service-categories/, services/, workshop/services|products/
    path(
        "api/", include("apps.workshops.urls")
    ),  # workshop/me|page|operation-hours|point/, points-of-interest/
    path(
        "api/", include("apps.vehicles.urls")
    ),  # vehicles/, workshop/vehicles/{id}/history/
    path(
        "api/", include("apps.attendances.urls")
    ),  # attendances/, budgets/, workshop/attendances|budgets|clients/
    path("api/", include("apps.chat.urls")),  # chats/
    path(
        "api/", include("apps.reviews.urls")
    ),  # reviews/, denunciations/, workshop/reviews/
    path(
        "api/", include("apps.promotions.urls")
    ),  # workshop/promotions/ (públicas na Fase 4)
    path("api/", include("apps.notifications.urls")),  # notifications/ (Fase 4)
    # Administração/moderação (BE-035): só is_staff; rotas em BE-073/BE-074.
    path("api/admin/", include("apps.moderation.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
