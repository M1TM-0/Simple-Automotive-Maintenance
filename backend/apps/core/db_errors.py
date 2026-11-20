from rest_framework import status

from .exceptions import ApiConflict, ApiServiceUnavailable, ApiValidationFailure
from .limits import NUL_MESSAGE

RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
# ON DELETE RESTRICT: PostgreSQL até 16 reporta 23503; a partir do 18, 23001.
RESTRICT_VIOLATION = "23001"
NOT_NULL_VIOLATION = "23502"
CHECK_VIOLATION = "23514"
RAISE_EXCEPTION = "P0001"
NUL_TEXT_ERROR = "NUL (0x00)"

# constraint/índice -> (status HTTP, campo ou None, mensagem)
CONSTRAINT_ERRORS = {
    "uq_client_email": (409, "email", "Este e-mail já está em uso."),
    "uq_workshop_email": (409, "email", "Este e-mail já está em uso."),
    "workshop_cnpj_key": (409, "cnpj", "Já existe uma oficina com este CNPJ."),
    "unique_vehicle": (400, "plate", "Já existe um veículo com esta placa."),
    "unique_favorite": (409, None, "Esta oficina já está nos favoritos."),
    "uq_chat_client_workshop": (
        409,
        None,
        "Já existe uma conversa entre este cliente e esta oficina.",
    ),
    "review_id_budget_key": (409, None, "Você já avaliou este atendimento."),
    "uq_ws_workshop_service": (
        409,
        "id_service",
        "Este serviço já foi adicionado à oficina.",
    ),
    "uq_ws_custom_name": (
        409,
        "name_local",
        "Já existe um serviço personalizado com este nome.",
    ),
    "uq_service_name_normalized": (
        409,
        "name",
        "Já existe um serviço com este nome.",
    ),
    "uq_budget_one_pending": (
        409,
        None,
        "O atendimento já possui um orçamento pendente.",
    ),
    "uq_budget_one_approved": (
        409,
        None,
        "O atendimento já possui um orçamento aprovado.",
    ),
    "workshop_id_point_of_interest_key": (
        409,
        "id_point_of_interest",
        "Este ponto do mapa já está vinculado a outra oficina.",
    ),
    "uq_poi_external": (409, None, "Este ponto de interesse já foi importado."),
    "uq_denunciation_open_review": (
        409,
        None,
        "Você já denunciou este conteúdo e ele está em análise.",
    ),
    "uq_denunciation_open_promotion": (
        409,
        None,
        "Você já denunciou este conteúdo e ele está em análise.",
    ),
    "uq_denunciation_open_advertisement": (
        409,
        None,
        "Você já denunciou este conteúdo e ele está em análise.",
    ),
    "ck_vehicle_plate": (400, "plate", "Placa inválida."),
    "ck_vehicle_mileage": (400, "mileage_km", "A quilometragem não pode ser negativa."),
    "ck_poi_latitude": (400, "latitude", "Latitude deve estar entre -90 e 90."),
    "ck_poi_longitude": (400, "longitude", "Longitude deve estar entre -180 e 180."),
    "ck_operation_hour_day": (
        400,
        "day_of_week",
        "Dia da semana deve estar entre 1 e 7.",
    ),
    "ck_operation_hour_interval": (
        400,
        "closing_time",
        "O horário de fechamento deve ser posterior ao de abertura.",
    ),
    "ck_vehicle_year_fabrication": (
        400,
        "year_fabrication",
        "Ano de fabricação inválido.",
    ),
    "ck_vehicle_year_model": (400, "year_model", "Ano do modelo inválido."),
    "ck_workshop_cnpj": (400, "cnpj", "CNPJ inválido."),
}

GENERIC_VALIDATION = "Os dados informados violam uma regra de validação."
GENERIC_DEPENDENCY = "Este registro possui dependências e não pode ser removido."
GENERIC_REFERENCE = "O registro referenciado não existe ou não está disponível."
GENERIC_DUPLICATE = "Já existe um registro com estes dados."


def _driver_error(exc):
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "sqlstate", None):
            return current
        current = current.__cause__ or current.__context__
    return None


def sqlstate_of(exc):
    driver = _driver_error(exc)
    return getattr(driver, "sqlstate", None) if driver else None


def db_error_details(exc):
    """`(sqlstate, constraint, mensagem principal)` do erro do PostgreSQL, ou Nones."""
    driver = _driver_error(exc)
    diag = getattr(driver, "diag", None)
    return (
        getattr(driver, "sqlstate", None),
        getattr(diag, "constraint_name", None),
        getattr(diag, "message_primary", None),
    )


def is_retryable(exc):
    return sqlstate_of(exc) in RETRYABLE_SQLSTATES


def _failure(status_code, field, message):
    if status_code == status.HTTP_409_CONFLICT:
        return ApiConflict({field: [message]} if field else message)
    return ApiValidationFailure({field: [message]} if field else {"detail": message})


def translate_db_error(exc):
    """Converte erros do PostgreSQL (constraints e triggers) em respostas HTTP.

    Devolve None quando o erro não é tratado: o chamador responde 500 genérico.
    """
    driver = _driver_error(exc)
    if driver is None:
        # O psycopg recusa `\x00` em texto antes de enviar (sem SQLSTATE). Os campos e
        # a busca já validam (BE-086); isto evita 500 numa entrada que escape.
        if NUL_TEXT_ERROR in str(exc):
            return ApiValidationFailure({"detail": NUL_MESSAGE})
        return None

    sqlstate = driver.sqlstate
    diag = getattr(driver, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    primary = getattr(diag, "message_primary", None)

    if sqlstate in RETRYABLE_SQLSTATES:
        return ApiServiceUnavailable()

    if sqlstate == UNIQUE_VIOLATION:
        if constraint in CONSTRAINT_ERRORS:
            return _failure(*CONSTRAINT_ERRORS[constraint])
        if constraint is None and primary:
            # RAISE ... USING ERRCODE = 'unique_violation' numa função (ex.:
            # approve_workshop_service_request): a mensagem é do schema, em português.
            return ApiConflict(primary)
        return ApiConflict(GENERIC_DUPLICATE)

    if sqlstate == RESTRICT_VIOLATION:
        return ApiConflict(GENERIC_DEPENDENCY)

    if sqlstate == FOREIGN_KEY_VIOLATION:
        if primary and primary.startswith("update or delete"):
            return ApiConflict(GENERIC_DEPENDENCY)
        return ApiValidationFailure({"detail": GENERIC_REFERENCE})

    if sqlstate == CHECK_VIOLATION:
        if constraint:
            if constraint in CONSTRAINT_ERRORS:
                return _failure(*CONSTRAINT_ERRORS[constraint])
            return ApiValidationFailure({"detail": GENERIC_VALIDATION})
        return ApiConflict(primary or GENERIC_VALIDATION)

    if sqlstate == RAISE_EXCEPTION:
        return ApiConflict(primary or GENERIC_VALIDATION)

    if sqlstate == NOT_NULL_VIOLATION:
        return ApiValidationFailure(
            {"detail": "Há campos obrigatórios não informados."}
        )

    if sqlstate.startswith("22"):
        return ApiValidationFailure({"detail": "Dados inválidos."})

    return None
