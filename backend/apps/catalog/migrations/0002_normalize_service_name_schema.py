"""BE-094 — `normalize_service_name()` chama `clean_service_name()` com o schema.

Achado no ensaio real de restauração do staging: o `pg_dump` grava
`SELECT pg_catalog.set_config('search_path', '', false)` no início do dump e o
`pg_restore` recria o índice `uq_service_name_normalized` (e o de WORKSHOP_SERVICE) com
esse `search_path` vazio. A função do `init.sql` chama `clean_service_name(p_name)` sem
schema → "function clean_service_name(text) does not exist" e a restauração inteira é
desfeita (transação única): **nenhum backup era restaurável**, em qualquer versão do
PostgreSQL. É a mesma raiz da P-21 (PostgreSQL 17+ roda o `CREATE INDEX` com
`search_path` restrito).

Correção mínima e compatível: mesma função, mesmo resultado, só a chamada qualificada
(`public.clean_service_name`). Continua `IMMUTABLE`/`STRICT`/`PARALLEL SAFE` e
"inlinável" (os índices por expressão continuam valendo; nenhum dado muda, nada a
reindexar). O `init.sql` não é alterado aqui (fonte da verdade; a correção dele — P-21 —
é decisão do responsável); esta migration vale para bancos novos e existentes.
"""

from django.db import migrations

FIXED = """
CREATE OR REPLACE FUNCTION public.normalize_service_name(p_name TEXT)
RETURNS TEXT AS $$
    SELECT LOWER(public.clean_service_name(p_name));
$$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;
"""

ORIGINAL = """
CREATE OR REPLACE FUNCTION public.normalize_service_name(p_name TEXT)
RETURNS TEXT AS $$
    SELECT LOWER(clean_service_name(p_name));
$$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_init_schema"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=FIXED, reverse_sql=ORIGINAL),
    ]
