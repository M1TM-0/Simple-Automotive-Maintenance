import logging

from django.conf import settings
from django.core.exceptions import (
    RequestDataTooBig,
    TooManyFieldsSent,
    TooManyFilesSent,
)
from django.db import DatabaseError
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("sam.api")

NON_FIELD_ERRORS_KEY = "non_field_errors"


class ApiConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A operação conflita com o estado atual do recurso."
    default_code = "conflict"


class ApiValidationFailure(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Dados inválidos."
    default_code = "invalid"


class ApiServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "O serviço está temporariamente indisponível. Tente novamente."
    default_code = "unavailable"


class ApiPayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "A requisição excede o tamanho permitido."
    default_code = "payload_too_large"


class ApiThrottled(Throttled):
    """429 com mensagem em português (a tradução do DRF é exibida no login)."""

    default_detail = "Muitas requisições em pouco tempo."
    extra_detail_singular = "Tente novamente em {wait} segundo."
    extra_detail_plural = "Tente novamente em {wait} segundos."


def sam_exception_handler(exc, context):
    if isinstance(exc, Throttled) and not isinstance(exc, ApiThrottled):
        exc = ApiThrottled(wait=exc.wait)

    # Rede de segurança (BE-086): o RequestSizeLimitMiddleware já recusa pelo
    # Content-Length; isto cobre corpo sem o cabeçalho e excesso de campos/arquivos.
    if isinstance(exc, RequestDataTooBig):
        exc = ApiPayloadTooLarge()
    elif isinstance(exc, (TooManyFieldsSent, TooManyFilesSent)):
        exc = ApiValidationFailure("Campos ou arquivos demais na requisição.")

    if isinstance(exc, DatabaseError):
        from .db_errors import translate_db_error

        translated = translate_db_error(exc)
        if translated is not None:
            exc = translated

    response = drf_exception_handler(exc, context)

    if response is None:
        if settings.DEBUG:
            return None
        logger.exception("Erro não tratado em %s", _view_name(context))
        return Response(
            {"detail": "Erro interno do servidor."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(response.data, list):
        response.data = {NON_FIELD_ERRORS_KEY: response.data}

    if isinstance(exc, ApiServiceUnavailable):
        response["Retry-After"] = "1"

    return response


def _view_name(context):
    view = context.get("view")
    return type(view).__name__ if view is not None else "view desconhecida"
