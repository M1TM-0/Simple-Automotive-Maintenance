from django.core.checks import Error, Tags, register
from django.db import OperationalError, connections

MIN_POSTGRES_VERSION = 130000


@register(Tags.database)
def check_postgresql_version(app_configs, databases=None, **kwargs):
    errors = []

    for alias in databases or []:
        connection = connections[alias]

        if connection.vendor != "postgresql":
            errors.append(
                Error(
                    f"O banco '{alias}' não é PostgreSQL. O SAM requer PostgreSQL 13 ou superior.",
                    id="sam.E001",
                )
            )
            continue

        try:
            version = connection.pg_version
        except OperationalError as exc:
            errors.append(
                Error(
                    f"Não foi possível conectar ao banco '{alias}': {exc}",
                    id="sam.E003",
                )
            )
            continue

        if version < MIN_POSTGRES_VERSION:
            errors.append(
                Error(
                    "O SAM requer PostgreSQL 13 ou superior "
                    f"(versão atual: {version // 10000}.{version % 10000}).",
                    id="sam.E002",
                )
            )

    return errors
