# Convenção de migrations (P-18 / BE-007, BE-091)

O schema nasce do `database/init.sql` (ADR 0001), aplicado **uma única vez** pela
migration `core/0001` num banco vazio. Tudo o que vem depois é migration do Django, com
SQL explícito. Esta convenção é o que permite a implantação sem parada longa e a volta
de versão do `deploy/deploy.sh`.

## Regras

1. **Nunca edite o `init.sql` para mudar um banco existente** e nunca o reexecute à mão.
   Correção no `init.sql` só vale para bancos novos; o banco em produção muda por
   migration.
2. **Uma migration por mudança, no app dono da tabela** (ex.: `vehicles/0004`), com
   `migrations.RunSQL(sql=…, reverse_sql=…)`. Ida e volta obrigatórias: o teste
   `test_migrations_are_reversible_and_reapplicable` volta e reaplica as migrations.
3. **Modelo `managed=False`** acompanha a tabela (`CreateModel`/`AlterField` na mesma
   migration, com `options={"managed": False, "db_table": …}`), e
   `makemigrations --check` precisa ficar limpo.
4. **Views `SELECT p.*`**: alterar `PROMOTION` exige `DROP VIEW` + `CREATE VIEW` de
   `vw_promotion_effective` (e de `vw_advertisement_effective`, que depende dela) na
   mesma migration, ida e volta. O mesmo vale para `vw_vehicle_maintenance_history` ao
   mexer no histórico (veja `vehicles/0003`).
5. **Compatível com a versão anterior** (expandir → migrar → contrair). A implantação
   roda o `migrate` com a imagem nova **antes** de trocar a versão no ar, e a volta de
   versão (`deploy.sh --rollback`) não desfaz o schema. Então:
   - coluna nova: nula ou com `DEFAULT` (o código antigo não a preenche);
   - renomear/remover coluna: em duas implantações — primeiro o código deixa de usar,
     depois a migration remove;
   - `NOT NULL` em coluna existente: preencha antes (migration de dados), restrinja
     depois;
   - CHECK/trigger novos não podem recusar o que a versão anterior grava.
6. **Atomicidade**: cada migration roda numa transação (padrão do Django no
   PostgreSQL). Se falhar, nada fica pela metade e o `deploy.sh` para com a versão
   anterior no ar. `atomic = False` só com motivo escrito (hoje só a `core/0001`).
   `CREATE INDEX CONCURRENTLY` (tabela grande em produção) exige `atomic = False` e uma
   migration só para ele.
7. **Dados**: migration de dados (`RunPython`) com função reversa ou `noop` justificado;
   nunca dados fictícios em produção (o catálogo inicial já vem do `init.sql`).
8. **Erros do banco**: constraint nova com nome; se ela puder ser violada pela API,
   mapeie em `apps/core/db_errors.py` (409 com o campo) e teste.
9. **Depois de mudar o schema**: `python manage.py schema_diagram` (atualiza
   `docs/DIAGRAMA_SAM.svg`; um teste reprova o diagrama desatualizado) e, se a tabela
   for nova, confira a limpeza de tabelas `managed=False` dos testes transacionais
   (`backend/conftest.py`).

## Antes de commitar

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.test venv/bin/python manage.py makemigrations --check --dry-run
venv/bin/pytest apps/core/tests/test_chat_migration_and_jobs.py apps/core/tests/test_schema_and_models.py tests/deploy/test_artifacts.py
```

## Em produção

`deploy/deploy.sh` faz: backup → `migrate` (imagem nova, contêiner avulso) →
`createcachetable` → `check_schema` → troca de versão → verificação. Migration que falha
interrompe a implantação sem tocar a versão no ar (provado em
`tests/deploy/test_deploy_script.py` e no `deploy/smoke-test.sh`). Desfazer uma migration
já aplicada é manual: `python manage.py migrate <app> <migration_anterior>` (usa o
`reverse_sql`) ou restauração do backup — ver `backend/docs/RUNBOOK.md`.

## Funções SQL e `pg_restore` (BE-094)

O `pg_dump` grava `SELECT pg_catalog.set_config('search_path', '', false)` e o
`pg_restore` recria índices, constraints e colunas geradas com esse `search_path` vazio.
Uma função usada nesses objetos que chame outra função **sem schema** quebra a
restauração inteira (foi o caso de `normalize_service_name()`, corrigida pela
`catalog/0002_normalize_service_name_schema`). Em função nova ou alterada, qualifique as
chamadas (`public.clean_service_name(...)`) e prove com
`apps/catalog/tests/test_restore_search_path.py` (reconstrói os índices com `search_path`
vazio) ou com o ensaio `deploy/staging/staging.sh restore-drill`.

**P-21 (18/11/2026):** a mesma correção foi feita no próprio `database/init.sql`, que
passou a aplicar em banco vazio no PostgreSQL 17+ (o `CREATE INDEX` desde o 17 roda as
funções do índice com `search_path = pg_catalog, pg_temp`). A `core/0001` não mudou. A
`catalog/0002` continua necessária para os bancos criados antes da correção; em banco
novo ela reescreve a função com o mesmo texto (sem efeito). Seu `reverse_sql` devolve a
versão sem schema — desfazê-la num banco novo reintroduz o defeito do `pg_restore`; não
desfaça a `catalog/0002`. Prova: `apps/catalog/tests/test_init_sql_search_path.py`
(recria a função **a partir do texto do `init.sql`** e reconstrói os índices com o
`search_path` do PostgreSQL 17+, mais o controle negativo sem o schema).
