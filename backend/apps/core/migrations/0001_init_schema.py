from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import migrations

SCHEMA_PROBE = """
SELECT to_regclass('public.client') IS NOT NULL,
       to_regprocedure('public.run_expiration_jobs()') IS NOT NULL
"""


def apply_init_sql(apps, schema_editor):
    connection = schema_editor.connection

    if connection.vendor != "postgresql":
        raise ImproperlyConfigured("O SAM requer PostgreSQL 13 ou superior.")

    path = settings.SAM_INIT_SQL_PATH
    if not path or not path.is_file():
        raise ImproperlyConfigured(
            f"init.sql não encontrado em '{path}'. Ajuste SAM_INIT_SQL_PATH."
        )

    with connection.cursor() as cursor:
        cursor.execute(SCHEMA_PROBE)
        has_tables, has_functions = cursor.fetchone()

    if has_tables and has_functions:
        return

    if has_tables or has_functions:
        raise ImproperlyConfigured(
            "O banco contém um schema do SAM incompleto. Recrie o banco vazio e execute 'migrate'."
        )

    raw = connection.connection
    try:
        raw.execute(path.read_text(encoding="utf-8"))
    except Exception:
        raw.rollback()
        raise


class Migration(migrations.Migration):
    """Aplica database/init.sql, a fonte da verdade do schema, uma única vez.

    Não é atômica porque o init.sql controla a própria transação (BEGIN/COMMIT).
    Não é reversível: para recomeçar, recrie o banco.
    """

    atomic = False
    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(apply_init_sql),
    ]
