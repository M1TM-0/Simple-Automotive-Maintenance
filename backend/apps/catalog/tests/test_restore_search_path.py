"""BE-094 — Regressão: o banco precisa ser restaurável pelo `pg_restore`.

O `pg_restore` recria os índices com `search_path` vazio (o `pg_dump` grava
`set_config('search_path', '', false)`). Com `normalize_service_name()` chamando
`clean_service_name()` sem schema, o índice `uq_service_name_normalized` falhava e a
restauração inteira era desfeita (achado no ensaio real do staging). Aqui a mesma
condição é reproduzida sem precisar de `pg_dump` da mesma versão do servidor.
"""

import pytest
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

INDEXES = ("public.uq_service_name_normalized", "public.uq_ws_custom_name")


def rebuild_indexes_like_pg_restore():
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.set_config('search_path', '', true)")
        cursor.execute("SELECT public.normalize_service_name('  Troca   de  ÓLEO ')")
        value = cursor.fetchone()[0]
        for index in INDEXES:
            cursor.execute(f"REINDEX INDEX {index}")  # sql-safe: nomes fixos acima
    return value


def index_names():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexrelid::regclass::text FROM pg_index "
            "WHERE pg_get_indexdef(indexrelid) LIKE '%normalize_service_name%'"
        )
        return sorted(row[0] for row in cursor.fetchall())


@pytest.mark.django_db
def test_indexes_using_the_function_rebuild_with_an_empty_search_path():
    assert index_names() == sorted(i.removeprefix("public.") for i in INDEXES)

    assert rebuild_indexes_like_pg_restore() == "troca de óleo"


@pytest.mark.django_db(transaction=True)
def test_migration_goes_back_to_the_original_function_and_forward_again():
    executor = MigrationExecutor(connection)
    executor.migrate([("catalog", "0001_initial")])
    try:
        # Sem a migration: exatamente o erro do pg_restore do staging.
        with pytest.raises(DatabaseError, match="clean_service_name"):
            rebuild_indexes_like_pg_restore()
    finally:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    assert rebuild_indexes_like_pg_restore() == "troca de óleo"
