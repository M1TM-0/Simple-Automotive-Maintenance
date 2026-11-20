# ADR 0001 — init.sql como fonte da verdade do schema

- **Status:** Aceito por padrão — recomendação do backlog (DP-01), 2026-11
- **Tarefas:** BE-001, BE-007, BE-014, BE-091

## Contexto

O banco do SAM depende de recursos que o ORM do Django não gera: chaves compostas,
colunas geradas (`subtotal`, `item_type`…), 16 triggers que guardam a máquina de estados
do atendimento, o ciclo do orçamento, o histórico só-inclusão e as promoções, além de 26
funções. O `database/init.sql` já existia, testado em PostgreSQL 16.

## Decisão

- `database/init.sql` é a fonte da verdade. A migration `core/0001` o executa **uma vez**
  (não atômica, porque o arquivo controla a própria transação); sonda o schema e recusa
  um banco com schema parcial.
- Modelos Django `managed=False`; colunas geradas como `GeneratedField` somente leitura.
- Mudança posterior = migration `RunSQL` com ida **e volta** no app dono da tabela;
  alterar `PROMOTION` exige recriar `vw_promotion_effective` (as views usam `SELECT p.*`).
  Convenção completa: `backend/docs/migrations.md`.

## Consequências

- O `init.sql` nunca é reexecutado à mão; `manage.py check_schema` (BE-091) confere, a
  cada implantação, que cada tabela/view/tipo/função/trigger/índice declarado existe.
- Funções usadas por índices/constraints chamam outras funções **com schema**
  (`public.clean_service_name` em `normalize_service_name()`): o PostgreSQL 17+ roda
  `CREATE INDEX`/`REINDEX` com `search_path` restrito e o `pg_restore` com `search_path`
  vazio. Corrigido no próprio `init.sql` em 18/11/2026 (P-21, decisão do responsável);
  validado em banco vazio no PostgreSQL 16 e 18 (`apps/catalog/tests/test_init_sql_search_path.py`).
- Tabelas de operação novas (`MAINTENANCE_REMINDER`, `JOB_HEARTBEAT`) seguem a mesma
  convenção (`RunSQL` + modelo `managed=False`).
