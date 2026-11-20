import re
import uuid

from .logging import log_user_var, request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIDMiddleware:
    """Atribui um identificador a cada requisição e o devolve no cabeçalho de resposta."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex

        request.request_id = request_id
        id_token = request_id_var.set(request_id)
        user_token = log_user_var.set("anonymous")

        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(id_token)
            log_user_var.reset(user_token)

        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestSizeLimitMiddleware:
    """Recusa com 413 um corpo maior que o limite, antes de qualquer leitura (BE-086).

    O limite vem do `Content-Length`: `SAM_MAX_UPLOAD_BYTES` para multipart (até 3
    fotos de `SAM_IMAGE_MAX_BYTES` + campos) e `SAM_MAX_BODY_BYTES` para o resto
    (JSON). Corpo sem `Content-Length` não é lido além do que o servidor WSGI entrega;
    em produção o Nginx limita de novo (`client_max_body_size`, BE-089). Fica depois do
    CorsMiddleware para o navegador conseguir ler o 413.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.http import JsonResponse

        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return JsonResponse(
                {"detail": "Cabeçalho Content-Length inválido."}, status=400
            )

        multipart = request.META.get("CONTENT_TYPE", "").startswith("multipart/")
        limit = (
            settings.SAM_MAX_UPLOAD_BYTES if multipart else settings.SAM_MAX_BODY_BYTES
        )
        if length > limit:
            return JsonResponse(
                {"detail": f"A requisição excede o limite de {_megabytes(limit)} MB."},
                status=413,
            )
        return self.get_response(request)


def _megabytes(size):
    value = size / (1024 * 1024)
    return (
        f"{value:.0f}"
        if value >= 10 or value.is_integer()
        else f"{value:.1f}".replace(".", ",")
    )
