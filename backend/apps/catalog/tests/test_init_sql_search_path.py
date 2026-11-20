"""P-21 — O `init.sql` aplica em PostgreSQL 17+ (índice com `search_path` restrito).

Desde o PostgreSQL 17, `CREATE INDEX`/`REINDEX` executam as funções do índice com
`search_path = pg_catalog, pg_temp`. O `normalize_service_name()` do `init.sql` chamava
`clean_service_name()` sem schema e a migration `core/0001` falhava em banco vazio
("function clean_service_name(text) does not exist"). Correção: chamada qualificada
(`public.clean_service_name`) no próprio `init.sql`.

O banco de teste já recebe a mesma função pela `catalog/0002`; por isso os testes
recriam a função **a partir do texto do `init.sql`** (transação desfeita no fim) e
reconstroem os índices com o `search_path` do PostgreSQL 17+. Valem em qualquer versão:
no 16 o `search_path` restrito é imposto pelo teste.
"""

import re

import pytest
from django.conf import settings
from django.db import DatabaseError, connection, transaction

INDEXES = ("public.uq_service_name_normalized", "public.uq_ws_custom_name")
RESTRICTED_SEARCH_PATH = "pg_catalog, pg_temp"  # o que o PostgreSQL 17+ usa
DEFINITION = re.compile(
    r"CREATE OR REPLACE FUNCTION normalize_service_name\(.*?\$\$ LANGUAGE sql[^;]*;",
    re.DOTALL,
)


def init_sql_definition():
    found = DEFINITION.findall(settings.SAM_INIT_SQL_PATH.read_text(encoding="utf-8"))
    assert len(found) == 1, "normalize_service_name() deve ser definida uma vez"
    return found[0]


def build_indexes_like_pg17(definition):
    """Recria a função com `definition` e (re)constrói os índices como o PG 17+."""
    with connection.cursor() as cursor:
        cursor.execute(definition)
        cursor.execute(
            "SELECT pg_catalog.set_config('search_path', %s, true)",
            [RESTRICTED_SEARCH_PATH],
        )
        cursor.execute(
            "CREATE UNIQUE INDEX p21_probe "
            "ON public.service (public.normalize_service_name(name))"
        )
        for index in INDEXES:
            cursor.execute(f"REINDEX INDEX {index}")  # sql-safe: nomes fixos acima
        cursor.execute("SELECT public.normalize_service_name('  Troca   de  ÓLEO ')")
        return cursor.fetchone()[0]


def test_init_sql_qualifies_the_call_used_by_the_indexes():
    definition = init_sql_definition()

    assert "public.clean_service_name(p_name)" in definition
    assert "IMMUTABLE STRICT PARALLEL SAFE" in definition  # função preservada


@pytest.mark.django_db
def test_init_sql_function_builds_the_indexes_with_the_pg17_search_path():
    with transaction.atomic():
        assert build_indexes_like_pg17(init_sql_definition()) == "troca de óleo"
        transaction.set_rollback(True)


@pytest.mark.django_db
def test_unqualified_call_reproduces_the_pg17_failure():
    """Controle negativo: sem o schema, o mesmo roteiro dá o erro original da P-21."""
    unqualified = init_sql_definition().replace(
        "public.clean_service_name(", "clean_service_name("
    )

    with transaction.atomic():
        with pytest.raises(DatabaseError, match="clean_service_name"):
            build_indexes_like_pg17(unqualified)
        transaction.set_rollback(True)
