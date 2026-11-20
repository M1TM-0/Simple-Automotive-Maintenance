from django.http import JsonResponse
from django.views import defaults
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny


@extend_schema(exclude=True)
@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    raise NotFound("Endpoint não encontrado.")


def _is_api(request):
    return request.path.startswith("/api/")


def bad_request(request, exception=None):
    if _is_api(request):
        return JsonResponse({"detail": "Requisição inválida."}, status=400)
    return defaults.bad_request(request, exception)


def permission_denied(request, exception=None):
    if _is_api(request):
        return JsonResponse(
            {"detail": "Você não tem permissão para esta ação."}, status=403
        )
    return defaults.permission_denied(request, exception)


def csrf_failure(request, reason=""):
    """CSRF_FAILURE_VIEW: JSON na API (o frontend lê `detail`), HTML padrão fora dela."""
    if _is_api(request):
        return JsonResponse(
            {
                "detail": "Falha na verificação CSRF. Recarregue a página e tente de novo."
            },
            status=403,
        )
    from django.views.csrf import csrf_failure as default_csrf_failure

    return default_csrf_failure(request, reason=reason)


def not_found(request, exception=None):
    if _is_api(request):
        return JsonResponse({"detail": "Endpoint não encontrado."}, status=404)
    return defaults.page_not_found(request, exception)


def server_error(request):
    if _is_api(request):
        return JsonResponse({"detail": "Erro interno do servidor."}, status=500)
    return defaults.server_error(request)
