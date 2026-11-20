from drf_spectacular.utils import OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework import serializers

FieldErrors = inline_serializer(
    "FieldErrors",
    {"campo": serializers.ListField(child=serializers.CharField())},
)
DetailError = inline_serializer("DetailError", {"detail": serializers.CharField()})

ERROR_RESPONSES = {
    400: OpenApiResponse(
        FieldErrors,
        description="Validação por campo.",
        examples=[
            OpenApiExample(
                "Validação", value={"plate": ["Já existe um veículo com esta placa."]}
            )
        ],
    ),
    401: OpenApiResponse(DetailError, description="Não autenticado."),
    403: OpenApiResponse(DetailError, description="Sem permissão."),
    404: OpenApiResponse(DetailError, description="Inexistente ou de outro dono."),
    409: OpenApiResponse(
        DetailError,
        description="Conflito de estado ou duplicidade.",
        examples=[
            OpenApiExample(
                "Regra de negócio",
                value={
                    "detail": "O orçamento está fora da validade (venceu em 2026-11-01 18:00)."
                },
            )
        ],
    ),
    429: OpenApiResponse(DetailError, description="Limite de requisições excedido."),
}

PAGINATION_EXAMPLE = OpenApiExample(
    "Página",
    value={
        "count": 42,
        "next": "/api/attendances/?page=2",
        "previous": None,
        "results": [{"id": 7}],
    },
    response_only=True,
)


def paginated(serializer_class, name):
    """Envelope `{count, next, previous, results}` para `APIView` que pagina à mão com
    `SamPagination` (as views genéricas o recebem do drf-spectacular automaticamente)."""
    return inline_serializer(
        name,
        {
            "count": serializers.IntegerField(),
            "next": serializers.CharField(allow_null=True),
            "previous": serializers.CharField(allow_null=True),
            "results": serializer_class(many=True),
        },
    )


# Componente → campos que podem faltar na resposta. O drf-spectacular marca como
# obrigatório todo campo somente leitura; quando a resposta omite um campo de
# propósito (ex.: o chat traz só o interlocutor), o schema precisa dizer isso
# (`tests/contract/` valida as respostas reais em modo estrito, BE-081).
OPTIONAL_RESPONSE_FIELDS: dict[str, set[str]] = {}


def optional_response_fields(*names):
    """Decorador de serializer: estes campos não são obrigatórios no schema da resposta."""

    def decorate(serializer_class):
        component = serializer_class.__name__.removesuffix("Serializer")
        OPTIONAL_RESPONSE_FIELDS.setdefault(component, set()).update(names)
        return serializer_class

    return decorate


def drop_optional_response_fields(result, generator, request, public):
    """POSTPROCESSING_HOOK: tira de `required` os campos de `OPTIONAL_RESPONSE_FIELDS`."""
    schemas = result.get("components", {}).get("schemas", {})
    for component, names in OPTIONAL_RESPONSE_FIELDS.items():
        schema = schemas.get(component)
        if not schema or "required" not in schema:
            continue
        schema["required"] = [
            field for field in schema["required"] if field not in names
        ]
        if not schema["required"]:
            del schema["required"]
    return result
