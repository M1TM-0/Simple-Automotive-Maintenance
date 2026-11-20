> **Sobre este documento.** Este era o `README.md` da raiz durante o desenvolvimento:
> o plano de continuidade do backend, o estado por fase, as convenções e o registro das
> sessões de trabalho. Foi preservado aqui, sem alterações de conteúdo, como registro
> técnico do projeto. A apresentação pública do projeto está no [`README.md`](../README.md).
>
> - Os caminhos citados (`backend/…`, `deploy/…`, `frontend/…`) são relativos à raiz do repositório.
> - Referências a "README, seção N" em outros documentos e comentários do projeto
>   (`AUDITORIA.md`, `backend/docs/ACEITE.md`, `backlog/`, código) apontam para as seções deste arquivo.
> - Hashes de commit citados (por exemplo, `483a446`) pertencem ao histórico de
>   desenvolvimento anterior, que não foi publicado; este repositório começa num commit inicial único.

# SAM — Simple Automotive Maintenance

> *Your car • Your care* — plataforma web que conecta donos de veículos (**Cliente**) a oficinas e mecânicos (**Oficina**): mapa, solicitação de atendimento, orçamento, chat, histórico de manutenção, avaliações e promoções.

Este README é o **ponto de entrada e o plano de continuidade do backend**. Ele foi escrito para que o trabalho seja feito **fase por fase, em chats diferentes de IA, sem perder contexto**. Qualquer IA (ou pessoa) que assumir o projeto deve ler este arquivo inteiro antes de escrever código.

| Documento | Para que serve |
|---|---|
| `README.md` (este) | Estado atual, o que falta por fase e o **protocolo de trabalho** de cada sessão. |
| `AUDITORIA.md` | Auditoria das Fases 0–2 (17/11/2026): o que foi verificado, defeitos e pendências **P-01…P-20**. |
| `backlog/backlog_backend.md` | Especificação completa: 94 tarefas (BE-001…BE-094), contrato de API (seção 8), regras (seção 6), decisões (seção 15), testes (seção 11). **É a fonte da verdade do escopo.** |
| `backlog/backlog.md` | Requisitos do produto (RF, RNF, RN, MoSCoW). |
| `database/init.sql` | Schema, regras (triggers/funções) e seed. **Fonte da verdade do banco.** Leia os comentários. |
| `frontend/PENDENCIAS-API.md` e `frontend/js/api.js` | Contrato consumido pelo frontend (`api.js` é a única porta de dados). |

---

## 1. Visão rápida

| Camada | Tecnologia | Situação |
|---|---|---|
| Frontend | HTML + CSS + JS puro (26 telas), Leaflet | Integrado à API real (BE-072): `js/config.js` em `DRIVER:'http'`, `API_BASE:'http://localhost:8000'`. Mapa com tiles do OSM e duas fontes (SAM + OpenStreetMap pela Overpass, BE-094). E2E em Chromium e Firefox. |
| Backend | Python 3.12, Django 5.2.18, DRF 3.18.3, drf-spectacular, django-filter, Pillow, psycopg 3 (pool), Argon2, Gunicorn | Fases 0 a 7 implementadas; BE-094 validado no staging local, **aceite aguardando a assinatura do responsável** (`backend/docs/ACEITE.md`). |
| Banco | PostgreSQL 16 (mínimo 13; validado também no 18, P-21), schema por `database/init.sql` aplicado pela migration `core/0001` | Pronto, com migrations de ajuste (BE-008…BE-013). |
| Infra dev | Docker Compose: `db` (5432), `api` (8000, com healthcheck), `jobs` (expiração a cada 60 s, com batimento), `web` (frontend 5500) | Pronto. |
| Produção | `deploy/compose.prod.yml` + `deploy/deploy.sh`: PostgreSQL 16, API no Gunicorn (usuário sem root), `jobs`, Nginx (TLS, mesma origem, CSP), backup diário cifrado, monitor com alertas | Pronto; `deploy/smoke-test.sh` 42/42 com Docker de verdade (18/11/2026). Passo a passo: `backend/docs/RUNBOOK.md`. |
| Staging local | `deploy/staging/staging.sh`: a mesma implantação em `https://sam.localhost`, projeto `sam-staging` isolado do dev, só no loopback, CA local | No ar e validado (BE-094): `backend/docs/STAGING.md`. |

### Como rodar

```bash
# 1) Variáveis (raiz e backend): cria os .env que faltam com senha e SECRET_KEY aleatórias
./setup.sh

# 2) Subir tudo (migrate roda sozinho no serviço api)
docker compose up --build
#   API:       http://localhost:8000/api/health/   ·  Swagger: http://localhost:8000/api/docs/ (DEBUG)
#   Frontend:  http://localhost:5500/
```

Sem Docker (Postgres local):

```bash
cd backend
python3.12 -m venv venv && venv/bin/pip install -r requirements/dev.txt
# DATABASE_URL no backend/.env apontando para o seu Postgres
venv/bin/python manage.py migrate
venv/bin/python manage.py runserver 8000
```

### Como verificar (obrigatório ao final de toda sessão)

```bash
cd backend
venv/bin/ruff check .                                             # lint (o CI roda isto)
venv/bin/ruff format --check .                                    # formatação (bloqueante no CI desde a P-23)
DJANGO_SETTINGS_MODULE=config.settings.test venv/bin/python manage.py makemigrations --check --dry-run
venv/bin/python manage.py check --database default
venv/bin/pytest                                                   # PostgreSQL real; nunca SQLite
venv/bin/python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
```

Produção: `deploy/deploy.sh` (ver `backend/docs/RUNBOOK.md`); nunca `docker compose up` à mão com o `compose.prod.yml`.

Verificações das Fases 6 e 7 (o CI roda todas, ver `.github/workflows/backend-tests.yml`):

```bash
venv/bin/pytest --cov                     # cobertura: meta 90% geral (pyproject) …
venv/bin/coverage report --fail-under=95 --include="apps/*/services.py,apps/*/permissions.py,apps/*/selectors.py,apps/*/domain.py,apps/core/mixins.py"
venv/bin/pytest -m db_rules               # só as regras do banco (BE-079)
venv/bin/pytest -m e2e                    # E2E em Chromium e Firefox (BE-082/BE-094); fora do `pytest` padrão
SAM_STAGING_URL=https://sam.localhost venv/bin/pytest -m staging   # staging local no ar (BE-094)
DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=<64+ aleatórios> DEBUG=False \
  ALLOWED_HOSTS=sam.exemplo.com.br venv/bin/python manage.py check --deploy --fail-level WARNING
venv/bin/pip-audit -r requirements/dev.txt
venv/bin/pytest -m deploy                 # Gunicorn, Nginx×settings, deploy.sh, backup/restauração, diagrama (Fase 7)
../deploy/smoke-test.sh                   # implantação real com Docker (job deploy-smoke; precisa de acesso ao Docker)
# máquina de desenvolvimento: SAM_COMPOSE_OVERRIDE=$PWD/../deploy/staging/compose.staging.yml (só loopback)
```

> **Ensaio de backup (`tests/deploy/test_backup_restore.py`)**: precisa de `pg_dump`/`pg_restore` **da mesma versão** do servidor (o `pg_dump` 17+ grava `SET transaction_timeout`, que o PostgreSQL 16 não conhece). Com versões diferentes o teste é pulado; no CI (`SAM_REQUIRE_DEPLOY_TOOLS=1`, cliente 16 instalado) vira falha. Nesta máquina (cliente 18) rode contra um cluster PostgreSQL 18 descartável: `TEST_DATABASE_URL=postgres://…:55432/sam venv/bin/pytest -m deploy` (desde a correção da P-21 o `init.sql` original aplica no 18; não é mais preciso `SAM_INIT_SQL_PATH`).

Estado em 18/11/2026 (BE-094): **1992 testes passando** na suíte padrão (PostgreSQL 16; os 9 do ensaio de backup pulam com `pg_dump` de outra versão) + **51/51 de `-m deploy`** no PostgreSQL 18 (ferramentas da mesma versão) + **29 E2E** (`-m e2e`: 14 no Chromium, 14 no Firefox, 1 sem navegador) + **12 do staging** (`-m staging`), cobertura 97,22 % (≥ 95 % em serviços/permissões/seletores), `ruff`, `makemigrations --check`, `check`, `check --deploy`, `spectacular --validate --fail-on-warn` e `pip-audit` limpos. `deploy/smoke-test.sh`: 42/42.

Atualização 18/11/2026 (P-21 e P-23): suíte padrão **1995 passando** no PostgreSQL 16 (9 pulados: ensaio de backup) e **2004 passando** no PostgreSQL 18 (sem pulados, `init.sql` original), **29/29 E2E** (Chromium e Firefox), cobertura 97,22 % (98 % em serviços/permissões/seletores), `ruff check` e `ruff format --check` limpos (formatação bloqueante no CI).

> **E2E nesta máquina:** Playwright 1.65.2 (Chromium 159 e Firefox 159): `venv/bin/python -m playwright install chromium firefox`. O 1.41 anterior foi trocado porque o Firefox dele não reconhece CA local (ADR 0026). `SAM_E2E_BROWSERS=chromium|firefox` restringe; `SAM_E2E_CHROMIUM`/`SAM_E2E_FIREFOX` apontam outro binário.

> **PostgreSQL 17 ou mais novo na máquina local:** desde a correção da **P-21** (seção 4.2) o `init.sql` aplica sem ajuste no 16 e no 17+; basta `TEST_DATABASE_URL=postgres://… venv/bin/pytest`. A cópia corrigida por `sed` + `SAM_INIT_SQL_PATH` usada nas sessões anteriores não é mais necessária.

---

## 2. Decisões de arquitetura (BE-001)

**Na Fase 0, em BE-001, todas as decisões foram as recomendações sugeridas no backlog** (seção 15, coluna "Recomendação assumida"). Elas valem para todo o projeto; não as rediscuta, apenas siga-as. Os arquivos de ADR ainda não foram escritos (pendência P-12).

| DP | Decisão adotada |
|---|---|
| DP-01 | `init.sql` é a fonte do schema; migration `core/0001` o executa uma vez; modelos Django `managed=False`; mudanças futuras por `RunSQL` com ida e volta. |
| DP-02 | Autenticação própria sobre sessão Django + CSRF (sem JWT); `Principal(role, id, account)` em `request.user`. |
| DP-03 | Existe perfil admin/moderador: usuário Django `is_staff`; Django Admin provisório até haver T27/T28. |
| DP-04 | Imagens em sistema de arquivos (volume) atrás de storage abstrato. |
| DP-05 | `mileage_km` e `history_shared` no veículo; `interval_km` opcional (já criado em BE-013). |
| DP-06 | `setup_complete` = oficina com **≥ 1 serviço**; ponto e horários não são exigidos. |
| DP-07 | Oficina vê o histórico se `history_shared=true` **e** tiver ≥ 1 atendimento com o veículo. |
| DP-08 | Cliente e oficina cancelam até `in_progress`; sem restrição de atendimento duplicado. |
| DP-09 | Preço da divulgação configurável; pagamento confirmado manualmente pelo admin; sem gateway. |
| DP-10 | Pontos de interesse por importação idempotente de arquivo, respeitando a licença. |
| DP-11 | Notificações geradas pela aplicação (`on_commit`), `url` interna, sem e-mail. |
| DP-12 | Redefinição de senha com token assinado (sem tabela); SMTP configurável, console em dev. |
| DP-13 | Coluna `technical_notes` (feita); a oficina não edita dados cadastrais do veículo. |
| DP-14 | Sem etapa "aguardando peça". |
| DP-15 | Denúncia não oculta sozinha; `upheld` oculta; autor exibido como primeiro nome + inicial. |
| DP-16 | Fuso único `America/Sao_Paulo` (`SAM_TIME_ZONE`). |
| DP-17 | Mapa por caixa envolvente + Haversine, sem PostGIS; filtro de categoria retorna só oficinas. |
| DP-18 | Conta é desativada/anonimizada sob solicitação, preservando histórico. |
| DP-19 | Limites de texto = `maxlength` do frontend; busca por texto normalizado. |
| DP-20 | Oficina pública se `active` e com cadastro concluído; galeria fora do escopo. |
| DP-21 | Dev: API 8000, frontend 5500; produção na mesma origem via proxy. |
| DP-22 | Docker Compose + Nginx + TLS; backup diário; tiles do OSM público (ADR 0024); RPO 24 h / RTO 8 h (ADR 0025). |
| DP-23 | Nota média calculada na consulta; denormalizar só se o teste de carga exigir. |

Consequência para as tarefas condicionais: BE-012 e BE-013 (feitas), **BE-035, BE-073, BE-074, BE-076 e BE-078 entram no escopo** (todas feitas até a Fase 5); BE-077 (lembretes, *Could have*) foi pedida pelo responsável e feita na Fase 5.

ADRs: **26** em `backend/docs/adr/` (P-12 fechada na Fase 7; índice em `README.md` da pasta). Decisões do responsável no BE-094 (18/11/2026): tiles do OSM público e estabelecimentos do OSM pela Overpass (ADR 0024), **RPO 24 h / RTO 8 h** (ADR 0025), staging local e E2E em Chromium + Firefox, WebKit fora (ADR 0026). Decisões de segurança: `backend/docs/seguranca/`.

---

## 3. Estado por fase

| Fase | Tarefas | Concluídas e verificadas | Situação | Próxima ação |
|---|---:|---:|---|---|
| 0 — Preparação e arquitetura | 5 | 5 | ✅ Concluída (falta escrever os ADRs: P-12) | — |
| 1 — Banco e infraestrutura | 18 | 18 | ✅ Concluída (testes extras recomendados: P-13) | — |
| 2 — Autenticação e autorização | 12 | 12 | ✅ Concluída (branch `feat/fase-2-autenticacao`) | — |
| 3 — Módulos essenciais | 29 | 29 | ✅ Concluída (17/11/2026; notificações dos eventos ficam para BE-070) | — |
| 4 — APIs públicas e integração | 8 | 8 | ✅ Concluída (17/11/2026) | — |
| 5 — Funcionalidades complementares | 6 | 6 | ✅ Concluída (17/11/2026; BE-077 incluída a pedido do responsável) | — |
| 6 — Segurança e testes | 9 | 9 | ✅ Concluída (18/11/2026) | — |
| 7 — Implantação e finalização | 7 | 6 | 🟡 BE-094 implementado e validado no staging local (18/11/2026); **assinatura pendente** | Revisão e assinatura do responsável (`backend/docs/ACEITE.md`, seção 7); pendências ⏳ da seção 1 do aceite. |

\* Fase 2 fechada em 17/11/2026: pendências P-01…P-04, P-06…P-11, P-15 e P-19 resolvidas e testadas (ver seção 7).
\* Fase 3 fechada em 17/11/2026: 60 endpoints do contrato (seção 8 do backlog) implementados, no OpenAPI e testados; P-14 resolvida (ver seção 7).
\* Fase 4 fechada em 17/11/2026: 11 endpoints públicos/notificações, geração de notificações, `import_pois` e integração do frontend verificada no navegador (ver seção 7).
\* Fase 5 fechada em 17/11/2026: 6 rotas `/api/admin/*`, Django Admin (contas, catálogo, pontos, divulgações), pagamento manual e ativação das divulgações, anonimização de conta, próximas manutenções e lembretes (BE-077); 5 ADRs (ver seção 7).
\* Fase 6 fechada em 18/11/2026: matriz de autorização gerada do schema, suíte das regras do banco, concorrência com deadlock real, contrato estrito + normalizadores do frontend, E2E F1–F8, desempenho (N+1, EXPLAIN, carga), produção segura, limites de entrada e CI; 5 defeitos corrigidos (ver seção 7).
\* Fase 7 implementada em 18/11/2026: imagens de produção, Nginx, backup/restauração, `deploy.sh`, monitor e alertas, runbook, ADRs, diagrama gerado do banco; 1 defeito de segurança corrigido (IP do cliente). BE-094 (staging + assinatura) fica para o responsável.

> **Fase atual: 7 (aceite).** BE-094 implementado e validado no staging local; falta a revisão/assinatura do responsável e os itens ⏳ do `ACEITE.md` (runbook por outra pessoa, roteiro manual, observação do backup diário por alguns dias). Atualize esta linha e a tabela acima ao final de cada sessão.

---

## 4. O que falta, por fase

Formato: **ID — título** · prioridade · depende de · endpoints. Detalhes, escopo técnico e critérios de aceitação de cada tarefa estão em `backlog/backlog_backend.md` (procure por `#### BE-0NN`).

### 4.1 Fase 0 — Preparação e arquitetura (pendências de acabamento)

- [x] **P-12 / BE-001** — *(fechada na Fase 7: os 17 que faltavam; 23/23)* Escrever `backend/docs/adr/NNNN-titulo.md` (um por DP da seção 2, Status "Aceito por padrão — recomendação do backlog", data 2026-11) + `backend/docs/adr/README.md` ligando cada ADR às tarefas. *Feito na Fase 5:* o índice e os ADRs 0003, 0005, 0009, 0015 e 0018 (número do ADR = número da DP); faltam os outros 18.
- [x] **P-14 / BE-002** — `config/urls.py` (Fase 3): cada app declara os caminhos completos do contrato e é montado em `api/`; inclusão duplicada do catálogo e prefixos `api/catalog/`, `api/chat/`, `api/core/` removidos. Moderação em `/api/admin/` (Fase 2).
- [x] **P-16 / BE-003** — Varredura de segredos: gitleaks no CI (job `security`) e no pre-commit (Fase 6). *Feito na Fase 2:* `FRONTEND_BASE_URL`, `THROTTLE_*`, `LOGIN_LOCKOUT_*` e `CACHE_*` documentados em `backend/.env.example`.
- [x] **P-17 / BE-005** — *(Fase 7)* `setup.sh` cria os dois `.env` que faltam com segredos aleatórios (nunca sobrescreve); healthcheck da `api` e da `jobs` (batimento) no compose de desenvolvimento.

### 4.2 Fase 1 — Banco e infraestrutura (pendências de acabamento)

- [x] **P-13 / BE-016** — Testes de `SamPagination`, `SamModelSerializer` e `CommaSeparatedFilter` (`apps/core/tests/test_api_base.py`, Fase 6).
- [x] **P-18 / BE-007** — *(Fase 7)* `backend/docs/migrations.md` (RunSQL de ida e volta, views `SELECT p.*`, compatibilidade com a versão anterior para a volta do `deploy.sh`).
- [x] **P-20 / BE-006, BE-011** — Pool sob carga (gunicorn + `DB_POOL_MAX=10`, 1000 usuários sem erro) e `EXPLAIN` com volume (`tests/perf/`, ADR 0023), Fase 6.
- [x] **P-22 / BE-020** — *(resolvida na Fase 6: kwargs renomeados para `id_vehicle`, `id_budget`, `id_budget_item`, `id_client`; o contrato estrito valida as 89 operações)* *(achada na Fase 4)* No OpenAPI, várias rotas da Fase 3 têm o **nome** do parâmetro de caminho errado (o drf-spectacular usa a PK do `queryset` da view): ex. `/workshop/budgets/{id_attendance}/`, `/workshop/clients/{id_attendance}/vehicles/`. O comportamento está certo; só a documentação engana. Corrigir em BE-081 (testes de contrato) renomeando o kwarg da rota (como `workshop_id` nas rotas novas) ou com `OpenApiParameter`.
- [x] **P-23 / BE-087** — *(fechada em 18/11/2026, autorizada pelo responsável)* Formatação geral: commit exclusivo `483a446` (`style(backend): ruff format global`, `cd backend && venv/bin/ruff format .`, ruff 0.17.3) com **135 arquivos** (os 151 da Fase 6 menos os já formatados pelo pre-commit); AST idêntico antes/depois nos 281 `.py` versionados; suíte padrão no PostgreSQL 16 igual à de antes (1992 passed, 9 skipped). Hash em `.git-blame-ignore-revs` (localmente: `git config blame.ignoreRevsFile .git-blame-ignore-revs`). CI: `ruff format --check .` agora **bloqueante** (sem `continue-on-error`). Código novo precisa sair formatado (pre-commit `ruff-format` ou `venv/bin/ruff format .`). *(Fase 6: o código nunca tinha passado pelo `ruff format`; o CI rodava o formatador como informativo.)*
- [x] **P-21 / BE-007** — *(fechada em 18/11/2026, autorizada pelo responsável)* `normalize_service_name()` no `init.sql` agora chama `public.clean_service_name(p_name)`; a função foi preservada (`IMMUTABLE STRICT PARALLEL SAFE`, mesmo resultado) e a `core/0001` não mudou. **Evidências:** banco vazio com `psql -f init.sql` e com `manage.py migrate` no PostgreSQL **16.15** (compose) e **18.6** (cluster descartável) → 23 tabelas, 3 views, 16 triggers, 26 funções, 62 serviços, `check_schema` OK, `migrate` repetido não reaplica; índices `uq_service_name_normalized`/`uq_ws_custom_name` criados e reconstruídos com `search_path` `pg_catalog, pg_temp` (PG 17+) e vazio (`pg_restore`); unicidade normalizada → 23505; `pg_dump`/`pg_restore` no 18 OK. Antes da correção, o mesmo arquivo falhava no 18 na linha do `CREATE UNIQUE INDEX uq_service_name_normalized` e não criava nenhuma tabela. Suíte padrão: PG 16 1995 passaram + 9 pulados (ensaio de backup, `pg_dump` 18 × 16); PG 18 **2004 passaram** (inclui o ensaio de backup), sem `SAM_INIT_SQL_PATH`. Teste novo: `apps/catalog/tests/test_init_sql_search_path.py` (lê a função do próprio `init.sql`; reprova com o arquivo antigo, inclusive no PG 16). SQLSTATE de `RESTRICT`: 23503 no 16 e 23001 no 18, os dois → 409 (`db_errors.py`, `test_restrict_delete_maps_to_409` verde nas duas versões). A `catalog/0002` continua necessária para os bancos antigos e não deve ser desfeita (`backend/docs/migrations.md`). *(Achada na Fase 3: desde o PG 17, `CREATE INDEX` roda as funções com `search_path` restrito → `function clean_service_name(text) does not exist` na migration `core/0001`.)*

### 4.3 Fase 2 — Autenticação e autorização (✅ concluída em 17/11/2026)

Bloqueadoras:

- [x] **P-04** — `ruff check .` zerado (convenção de imports do projeto mantida: `apps` ordenado como terceiro).
- [x] **P-01 · BE-025/BE-030** — Visitante em endpoint protegido recebe **401** com `WWW-Authenticate: Session` (`authenticate_header`); perfil errado continua 403.
- [x] **P-02 · BE-031** — `PATCH /me/` com `ImageURLField` (multipart, `""`/`null` remove, imagem inválida → 400 no campo) e `apply_image_changes` (arquivo antigo apagado só após o commit). Foto da oficina vai para `PAG_WORKSHOP` e a remoção volta ao `default-profile.png`.
- [x] **P-03 · BE-031** — A sessão guarda o *fingerprint* (HMAC) do `password_hash`; troca, redefinição ou alteração da senha por fora derrubam as outras sessões. `POST /me/password/` → 204 e a sessão atual ganha chave nova.
- [x] **P-06 · BE-028/BE-030** — Testes da regra `setup_complete`, das 6 permissões, dos 2 mixins e da matriz 401/403/404 (sondas em `apps/core/tests/probe_urls.py`); `WORKSHOP_PERMISSIONS` × `WORKSHOP_WIZARD_PERMISSIONS` e um teste que percorre o URLconf exigindo `IsWorkshopSetupComplete` em toda rota `/workshop/*` fora do assistente.

Demais tarefas da fase:

- [x] **BE-028** — `setup_complete` (≥1 serviço; solicitação `rejected` não conta). `GET /workshop/attendances/` → 403 provado por sonda; BE-049 deve usar `WORKSHOP_PERMISSIONS`.
- [x] **BE-030** — Permissões por perfil e por objeto; mixins simplificados (`owner_lookup` aceita caminho aninhado, ex. `vehicle__client_id`).
- [x] **BE-031** — `PATCH /me/` e `POST /me/password/` (cliente e oficina; `email`/`cnpj`/`status` ignorados; senha atual errada → 400 em `current_password`).
- [x] **BE-033** — Throttles `login`/`register`/`reset`/`message`/`polling`; bloqueio progressivo (IP+conta e conta) com log `auth.lockout`; 429 em português com `Retry-After`; produção recusa cache local (padrão `DatabaseCache` + `createcachetable`). `MessageRateThrottle`/`PollingRateThrottle` serão declarados nas views de BE-058/BE-069.
- [x] **BE-035** — `apps/moderation/{permissions,views,audit}.py`: `AdminViewMixin` (is_staff + auditoria das escritas em `sam.audit`), login/logout/falha de admin auditados, `/api/admin/` montado. Rotas reais em BE-073/BE-074.
- [x] **Correções em tarefas já marcadas:** P-07 (22 testes de BE-032; falha de e-mail registrada em log), P-08 (CSRF, conta bloqueada, mesmo e-mail nos dois perfis, `rotate_token` + `flush` no login), P-09 (409 com `email`/`cnpj`, rollback testado), P-15 (CORS com `Origin`), P-19 (`inactive` → "Conta desativada…").
- [x] **P-05** — Commitado no branch `feat/fase-2-autenticacao` (`feat(backend): fase 2 — BE-024..BE-035`); falta abrir o PR para `main`.

### 4.4 Fase 3 — Módulos essenciais (29 tarefas) — ✅ concluída em 17/11/2026

Sugestão de blocos (checkpoints dentro da fase, nesta ordem):

Notificações citadas em BE-045/047/048/050/053/058/059/060 são de **BE-070 (Fase 4)**: os pontos de disparo estão listados na seção 6.

**Bloco 3A — Oficina e catálogo**
- [x] **BE-036** — Catálogo global (P1 · BE-016, BE-014) · `GET /service-categories/`, `GET /services/`. Busca `q` sem acentos (`oleo` acha “óleo”, DP-19), `Cache-Control` 300 s.
- [x] **BE-037** — Dados da oficina (P0 · BE-030, BE-028, BE-014, BE-016) · `GET/PATCH /workshop/me/`.
- [x] **BE-038** — Página pública (P1 · BE-037, BE-021) · `PATCH /workshop/page/`.
- [x] **BE-039** — Horários (P0 · BE-037, BE-017) · `GET/PUT /workshop/operation-hours/` (PUT atômico).
- [x] **BE-040** — Ponto no mapa (P1 · BE-037, BE-017) · `GET /points-of-interest/`, `POST /workshop/point/`.
- [x] **BE-041** — Serviços da oficina (P0 · BE-030, BE-014, BE-017, BE-022, BE-028) · `GET/POST /workshop/services/`, `PATCH /workshop/services/{id}/`. Duplicidade → 409 em `id_service`/`name_local`.
- [x] **BE-042** — Produtos (P1 · BE-030, BE-021, BE-014, BE-028) · `GET/POST /workshop/products/`, `PATCH /workshop/products/{id}/` (sem DELETE → 405). *A metade “some da listagem pública” do critério é provada em BE-066 (Fase 4), que cria a lista pública.*

**Bloco 3B — Veículos**
- [x] **BE-043** — Veículos do cliente (P0 · BE-030, BE-021, BE-022, BE-008, BE-014, BE-017) · `GET/POST /vehicles/`, `GET/PATCH/DELETE /vehicles/{id}/`.
- [x] **BE-044** — Histórico (P0 · BE-043, BE-014) · `GET/POST /vehicles/{id}/history/` (+ `GET /vehicles/{id}/history/{service-N|part-N}/`, que existe para PATCH/PUT/DELETE responderem 405).

**Bloco 3C — Atendimento e orçamento**
- [x] **BE-045** — Solicitar atendimento (P0 · BE-030, BE-014, BE-043, BE-028, BE-017) · `POST /attendances/`.
- [x] **BE-046** — Listar/detalhar (cliente) (P0 · BE-045, BE-016) · `GET /attendances/`, `GET /attendances/{id}/`.
- [x] **BE-047** — Cancelar (P1 · BE-046, BE-017) · `POST /attendances/{id}/cancel/`.
- [x] **BE-048** — Aprovar/recusar orçamento (P0 · BE-046, BE-017) · `POST /budgets/{id}/approve/`, `POST /budgets/{id}/reject/`.
- [x] **BE-049** — Atendimentos da oficina (P0 · BE-030, BE-046, BE-028) · `GET /workshop/attendances/`, `GET/PATCH /workshop/attendances/{id}/`.
- [x] **BE-050** — Transições e histórico (P0 · BE-049, BE-017, BE-043) · `POST /workshop/attendances/{id}/transition/`.
- [x] **BE-051** — Criar orçamento (P0 · BE-049, BE-017) · `POST /workshop/attendances/{id}/budget/`, `PATCH /workshop/budgets/{id}/`.
- [x] **BE-052** — Itens do orçamento (P0 · BE-051, BE-041, BE-017, BE-022) · `POST /workshop/budgets/{id}/items/`, `PATCH/DELETE /workshop/budgets/{b}/items/{i}/`.
- [x] **BE-053** — Enviar orçamento (P0 · BE-052, BE-017) · `POST /workshop/budgets/{id}/send/`.
- [x] **BE-054** — Execução dos itens (P0 · BE-050, BE-017) · `PATCH /workshop/budgets/{b}/items/{i}/execution/`.
- [x] **BE-055** — Clientes atendidos (P1 · BE-049) · `GET /workshop/clients/`, `GET /workshop/clients/{id}/vehicles/`.
- [x] **BE-056** — Histórico com autorização (P1 · BE-044, BE-055) · `GET /workshop/vehicles/{id}/history/` (403 com `detail` se não autorizado).

**Bloco 3D — Chat**
- [x] **BE-057** — Abrir/listar/detalhar (P0 · BE-030, BE-009, BE-014) · `GET /chats/`, `POST /chats/{workshopId}/open/`, `GET /chats/{id}/`.
- [x] **BE-058** — Mensagens e leitura (P0 · BE-057, BE-017) · `GET/POST /chats/{id}/messages/`, `POST /chats/{id}/read/`.

**Bloco 3E — Avaliações, denúncias, favoritos e promoções**
- [x] **BE-059** — Avaliar (P1 · BE-030, BE-046, BE-017) · `POST /reviews/`.
- [x] **BE-060** — Avaliações recebidas e resposta (P1 · BE-030, BE-059) · `GET /workshop/reviews/`, `POST /workshop/reviews/{id}/response/`.
- [x] **BE-061** — Denunciar (P1 · BE-030, BE-017) · `POST /denunciations/`.
- [x] **BE-062** — Favoritos (P2 · BE-030, BE-014) · `GET/POST /favorites/`, `DELETE /favorites/{id}/` (id = `id_workshop`).
- [x] **BE-063** — Promoções (P1 · BE-030, BE-021, BE-014, BE-017, BE-028) · `GET/POST /workshop/promotions/`, `PATCH /workshop/promotions/{id}/`.
- [x] **BE-064** — Divulgação paga (P2 · BE-063, BE-017) · `GET/POST /workshop/promotions/{id}/advertisements/`.

### 4.5 Fase 4 — APIs públicas e integração com o frontend (8 tarefas) — ✅ concluída em 17/11/2026

- [x] **BE-065** — Perfil público (P0 · BE-037, BE-039, BE-041, BE-022) · `GET /workshops/{id}/` (sem CNPJ/e-mail/responsável; `is_open_now` no fuso do negócio, `null` sem horários; `is_favorite` só para cliente; oficina não pública → 404).
- [x] **BE-066** — Produtos, promoções e avaliações públicas (P1 · BE-065, BE-042, BE-063, BE-059) · `GET /workshops/{workshop_id}/products/`, `/promotions/`, `/reviews/` (só `active`, só vigentes, só `published`).
- [x] **BE-067** — Pontos do mapa (P0 · BE-065, BE-014, BE-022) · `GET /map/points/` (UNION oficinas + POIs; caixa envolvente + Haversine; raio padrão 10 km, máximo 100 km → 400; página de 100).
- [x] **BE-068** — Promoções no ar (P1 · BE-063, BE-065) · `GET /promotions/` (divulgações em execução primeiro, depois promoções por `date_end`; cache 30 s).
- [x] **BE-069** — Notificações (P1 · BE-030, BE-010, BE-014) · `GET /notifications/` (`?unread=true`), `GET /notifications/unread-count/` (`PollingRateThrottle`), `POST /notifications/{id}/read/`, `POST /notifications/read-all/`.
- [x] **BE-070** — Geração de notificações (P1 · BE-069 + eventos de BE-045/047/048/053/050/058/059/060/023) · `apps/notifications/{events,services}.py`; rotina de expiração notifica orçamento vencido.
- [x] **BE-071** — Importação de pontos de interesse (P1 · BE-007, BE-014, BE-001) · `manage.py import_pois --file … --source … [--dry-run]` (CSV/GeoJSON; exemplos em `apps/workshops/tests/data/`).
- [x] **BE-072** — Integrar o frontend (DRIVER http) e reconciliar o contrato (P0 · BE-029, 027, 037, 067, 065, 058, 050, 052, 044). `api.js`: normalizador de T19 (`technical_notes`); `css/auth.css`: credencial demo oculta com `DRIVER:'http'` (FE-11); `PENDENCIAS-API.md`, `frontend/README.md` e `frontend/CLAUDE.md` atualizados.

### 4.6 Fase 5 — Funcionalidades complementares (6 tarefas) — ✅ concluída em 17/11/2026

- [x] **BE-073** — Moderação de denúncias (P2 · BE-035, BE-061, BE-017, BE-070) · `GET /admin/denunciations/` (`?status=`, `?target_type=`), `GET/PATCH /admin/denunciations/{id}/`, `POST /admin/reviews/{id}/hide/`. `upheld` tira o conteúdo do ar (avaliação `hidden`, promoção `inactive`, divulgação `cancelled`); denunciante notificado; auditoria em `sam.audit` (ADR 0015).
- [x] **BE-074** — Solicitações de serviço personalizado (P2 · BE-035, BE-041, BE-017, BE-070) · `GET /admin/service-requests/` (padrão: pendentes), `POST /admin/service-requests/{id}/approve/`, `.../reject/`. Funções do banco; reaproveitamento por nome normalizado provado com aprovações concorrentes.
- [x] **BE-075** — Django Admin de contas e catálogo (P2 · BE-035, BE-014). `apps/{accounts,catalog,workshops,promotions}/admin.py`; bloquear oficina → login 403 e some do mapa; `password_hash` fora do formulário.
- [x] **BE-076** — (Cond., entra pela DP-09) Pagamento manual e ativação das divulgações (P3 · BE-064, BE-035, BE-023). Confirmação no Django Admin; ativação e estorno na rotina `run_expiration_jobs` (ADR 0009).
- [x] **BE-077** — (Cond., *Could have*; pedida pelo responsável) Lembretes de manutenção preventiva (P3 · BE-013, BE-044, BE-070, BE-023) · `GET /vehicles/{id}/upcoming-maintenance/`; `manage.py send_maintenance_reminders` (no serviço `jobs`, a cada hora); um aviso por ciclo (tabela `MAINTENANCE_REMINDER`, ADR 0005). Frontend T12 ligado à API.
- [x] **BE-078** — (Cond., entra pela DP-18) Desativação e anonimização de conta (P3 · BE-025, BE-075, BE-001). Ações do Django Admin; anonimização irreversível com confirmação (ADR 0018).

### 4.7 Fase 6 — Segurança e testes (9 tarefas) — ✅ concluída em 18/11/2026

- [x] **BE-079** — Suíte das regras do banco (P1 · BE-015, BE-014) · `backend/tests/db_rules/` (`-m db_rules`): 64 + 16 combinações das funções de transição, 14 transições permitidas e 42 proibidas pelo trigger, SQLSTATE e mensagem; meta-teste exige positivo e negativo de cada uma das 16 triggers e 11 funções.
- [x] **BE-080** — Concorrência e deadlock (P1) · `backend/tests/concurrency/`: aprovar × expirar, aprovar × aprovar/recusar, `open` ×4, avaliação ×2, solicitação ×2, **deadlock real** com retentativa; `SAM_CONCURRENCY_ROUNDS`.
- [x] **BE-081** — Contrato (P1) · `backend/tests/contract/`: 89 operações com 2xx validado em modo estrito + normalizadores reais do `api.js` no Node. P-22 resolvida.
- [x] **BE-082** — E2E Playwright F1–F8 (P1) · `backend/tests/e2e/` (`-m e2e`): 8 fluxos + orçamento vencendo com a página aberta e avaliação duplicada.
- [x] **BE-083** — Desempenho (P2) · `backend/tests/perf/`: sem N+1 nas 38 leituras, sem `Seq Scan` em tabela grande, carga de polling (`polling_load.py`); ADR 0023.
- [x] **BE-084** — BOLA/IDOR (P0) · `backend/tests/security/test_authz_matrix.py`: matriz gerada do schema (401/403/404, vazamento, mass assignment, Django Admin); `backend/docs/seguranca/checklist-endpoints.md`.
- [x] **BE-085** — Produção segura (P1) · `config/settings/prod.py`, `check --deploy` sem avisos, e-mail de redefinição assíncrono; `backend/docs/seguranca/producao.md`.
- [x] **BE-086** — Entradas e limites (P1) · `apps/core/limits.py`, `RequestSizeLimitMiddleware` (413), fuzz dos parâmetros de consulta, proibição de SQL interpolado.
- [x] **BE-087** — Qualidade e CI (P2) · CI com lint, testes + cobertura (90%/95%), schema, `check --deploy`, `pip-audit`, gitleaks e E2E; `.pre-commit-config.yaml`; auditoria semanal das dependências.

### 4.8 Fase 7 — Implantação e finalização (7 tarefas) — 🟡 implementada em 18/11/2026; aceite pendente

- [x] **BE-088** — Imagem Docker de produção + Gunicorn (P1) · `backend/Dockerfile` (alvos `api` e `proxy`; contexto = raiz), `backend/gunicorn.conf.py`, `backend/docker/healthcheck.py`. SIGTERM espera a requisição em andamento (`tests/deploy/test_gunicorn.py`); usuário 10001. *Build real: `deploy/smoke-test.sh`, ainda não executado.*
- [x] **BE-089** — Proxy Nginx: HTTPS, estáticos, mesma origem (P1) · `deploy/nginx/`; CSP provada no Chromium (`tests/e2e/test_same_origin_csp.py`); `SAM_NUM_PROXIES` (defeito do `X-Forwarded-For` corrigido).
- [x] **BE-090** — Backup e restauração (banco + mídia) (P1) · `deploy/backup/` (`sam-backup`, `sam-restore`, `sam-backup-loop`); ensaio automatizado em `tests/deploy/test_backup_restore.py`.
- [x] **BE-091** — Migrations, seeds e atualização (P1) · `deploy/compose.prod.yml`, `deploy/deploy.sh`, `deploy/compose.sh`, `manage.py check_schema`, tabela `JOB_HEARTBEAT` (`core/0003`).
- [x] **BE-092** — Monitoramento e alertas (heartbeat do job) (P2) · `apps/core/monitoring.py`, `manage.py monitor`, `GET /api/health/jobs/`.
- [x] **BE-093** — Documentação de implantação e atualização dos documentos (P2) · `backend/docs/RUNBOOK.md`, `migrations.md`, ADRs, `docs/DIAGRAMA_SAM.svg` gerado (`manage.py schema_diagram`), frontend e `backlog.md` atualizados.
- [ ] **BE-094** — Validação final em staging e aceite (P0) · *(implementado e validado em 18/11/2026; aguardando assinatura)* Staging local `https://sam.localhost` (`deploy/staging/`, `backend/docs/STAGING.md`); mapa com tiles do OSM e estabelecimentos do OSM pela Overpass (`GET /map/external-points/`, ADR 0024); backup com md5 por tabela, agendador diário corrigido e ensaio de restauração isolado cronometrado (ADR 0025); E2E em Chromium e Firefox com HTTPS validado (ADR 0026). Evidências e pendências: `backend/docs/ACEITE.md`; relatório: `backend/docs/RELATORIO-BE-094.md`.

---

## 5. Protocolo de continuidade (para cada novo chat de IA)

O trabalho é feito **uma fase por sessão**. Cada sessão produz a **fase inteira** que estiver em andamento — 0, 1, 2, 3, 4, 5, 6, 7, nessa ordem — e só passa para a próxima quando a atual estiver concluída e verificada. Se a fase não couber em uma sessão, a sessão termina num checkpoint (bloco da seção 4) e a próxima continua **a mesma fase**.

### 5.1 Como descobrir o que fazer

1. Leia este README inteiro, depois `AUDITORIA.md`.
2. **Fase atual** = a primeira fase da seção 3 que não está ✅. Confirme olhando os checkboxes da seção 4 **e** o código (não confie só no checkbox: a auditoria mostrou tarefas marcadas com defeitos e tarefas desmarcadas já parcialmente feitas).
3. Leia no `backlog/backlog_backend.md` o texto completo de **cada** tarefa da fase (`#### BE-0NN`), as linhas da seção 8 com os endpoints dela, as regras da seção 6 que ela cita e o trecho do `init.sql` das tabelas envolvidas (triggers e mensagens de erro).
4. Leia `frontend/js/api.js` (e a tela que consome o endpoint) para conferir nomes de rotas, campos e formas de resposta que o frontend espera.
5. Rode a verificação da seção 1 **antes** de começar, para saber o ponto de partida.

### 5.2 Como executar a fase

1. Primeiro feche as pendências de acabamento das fases anteriores listadas na seção 4 que sejam bloqueadoras (marcadas "Bloqueadoras").
2. Implemente as tarefas na ordem de dependência (coluna "depende de"; blocos da Fase 3).
3. Para cada tarefa: código + testes que provem **cada critério de aceitação** do backlog + cenários negativos (401 sem sessão, 403 perfil errado, 404 recurso de outro dono, 400 validação, 409 regra do banco).
4. Ao concluir uma tarefa, marque `- [x] Concluída` no `backlog/backlog_backend.md` **e** o checkbox correspondente na seção 4 deste README.
5. Rode a verificação da seção 1 (ruff, migrations, check, pytest, spectacular). Tudo verde antes de encerrar.
6. Atualize a seção 3 (tabela e "Fase atual"), a seção 7 (registro de sessões) e, se descobrir algo que outra sessão precisa saber, a seção 6.
7. Commit por bloco ou por fase, mensagem `feat(backend): fase N — BE-0xx..BE-0yy` (peça autorização ao usuário antes de commitar/pushar se ele não tiver dado).

### 5.3 Definição de pronto de uma fase

- Todas as tarefas da fase com critérios de aceitação cobertos por testes que passam.
- `ruff check .` e `ruff format --check .` sem erros; `makemigrations --check` sem mudanças; `spectacular --validate --fail-on-warn` sem erros.
- Nenhum endpoint novo fora do OpenAPI; nenhum endpoint divergindo de `api.js` sem registro.
- Checkboxes do backlog e deste README atualizados; seção 3 mostra a fase como ✅; registro da sessão escrito.

### 5.4 Prompt para iniciar um novo chat

> Leia integralmente `README.md` e `AUDITORIA.md` na raiz do projeto SAM. Siga o protocolo da seção 5 do README: identifique a fase atual pela seção 3 e confirme no código, leia no `backlog/backlog_backend.md` todas as tarefas dessa fase, e **produza a fase inteira** (incluindo as pendências bloqueadoras das fases anteriores). Respeite as decisões da seção 2 (todas as recomendações do backlog foram aceitas em BE-001) e as convenções da seção 6. Ao final rode a verificação da seção 1, marque as tarefas concluídas no backlog e no README, atualize a seção 3 e registre a sessão na seção 7.

---

## 6. Convenções e armadilhas já conhecidas (leia antes de codar)

**Arquitetura**
- Camadas: `views` (HTTP) → `serializers` (forma/validação) → `services` (casos de uso, `@transactional`) → `models` (`managed=False`). Regra de negócio não fica em `views.py`.
- O banco é a autoridade das invariantes (triggers). O serviço faz a operação e **deixa o banco validar**; o erro é traduzido por `apps/core/db_errors.py` (23505/23514/P0001 → 409 com a mensagem do banco em `detail`). Valide campos antes para distinguir 400 de 409.
- Use `@transactional` (`apps/core/transactions.py`) nos serviços que escrevem: repete em deadlock (40P01/40001) e devolve 503 se esgotar.
- Recurso de outro dono → **404** (filtre o queryset pelo `request.user`; use `OwnedByClientMixin`/`OwnedByWorkshopMixin`, com `owner_lookup` aninhado se preciso). Perfil errado → 403. Sem sessão → 401.
- Nunca aceite do corpo: `id_client`, `id_workshop`, `status*`, `total_price`, `password_hash`.

**Modelos e banco**
- PKs são `GENERATED ALWAYS`: nunca envie `id` no INSERT. Colunas geradas (`subtotal`, `service_item_type`, `item_type`, `item_execution_status`) são `GeneratedField` somente leitura.
- `Budget.total_price` só a trigger escreve: salve `Budget` sempre com `update_fields=[...]`.
- Mudança de schema = migration `RunSQL` com ida e volta no app dono da tabela; se alterar `PROMOTION`, recrie `vw_promotion_effective` (as views usam `SELECT p.*`). Nunca reexecute o `init.sql` à mão.
- Grafias do banco são preservadas na API: atendimento `canceled`; orçamento/divulgação `cancelled`.
- O histórico (`REGISTER_MAINTENANCE*`) só cresce: sem PATCH/DELETE (405).

**API e contrato**
- Prefixo `/api/`, JSON snake_case, toda entidade com `id`, listas paginadas `{count,next,previous,results}` (`SamPagination`), dinheiro como string decimal, datas ISO-8601, `?status=a,b` via `CommaSeparatedFilter`.
- Erros: `400 {campo:[msg]}` (o frontend mapeia pelo nome do campo) ou `{detail}`. Para conflitos de unicidade, devolva o campo (`email`, `cnpj`, `plate`…).
- Imagens: use `ImageURLField` (serializer) + `apply_image_changes` (serviço). Campo vazio (`""`) remove a foto. Não use `CharField` para upload (foi a causa de P-02).
- Endpoints públicos (mapa, perfil, home, catálogo) usam `permission_classes=[AllowAny]` e não podem devolver CNPJ, e-mail ou responsável.
- Rotas da oficina (`/workshop/*`): `permission_classes = WORKSHOP_PERMISSIONS`; só as do assistente T17 (`me`, `page`, `operation-hours`, `point`, `services`, `points-of-interest`) usam `WORKSHOP_WIZARD_PERMISSIONS` (`apps/core/permissions.py`). Um teste percorre o URLconf e falha se uma rota nova esquecer.
- Rotas de admin (`/api/admin/*`): `class X(AdminViewMixin, <genérica do DRF>)` (`apps/moderation/views.py`) — exige `is_staff` e audita as escritas no logger `sam.audit` (`audit_action`, `audit_target_type` e, se quiser, `self.audit_extra`). Um teste percorre o URLconf e falha se uma rota `/api/admin/*` nova esquecer o mixin.
- Limites de taxa: chat `GET/POST /chats/{id}/messages/` declara `throttle_classes = [MessageRateThrottle, PollingRateThrottle]` (o primeiro só conta POST, o segundo só leituras); `GET /notifications/unread-count/` usa `PollingRateThrottle`. Todo 429 sai em português com `Retry-After` (`ApiThrottled`).
- Sessão: `apps/accounts/sessions.py` — chaves `sam_account_role`, `sam_account_id` e `sam_account_pwd` (*fingerprint* HMAC do `password_hash`; sem ele a sessão é recusada; as chaves legadas `role`/`id` não autenticam mais). Login/cadastro usam `start_account_session` (`flush` + `rotate_token`: o `csrftoken` muda após o login); troca de senha usa `refresh_account_session`.
- Fixtures de teste: `client_session`, `workshop_session`, `admin_session`, `api_client`, `account_session(conta, role)` e as fábricas em `apps/core/tests/factories.py` (inclui `deliver_attendance()` para levar um atendimento até `delivered`). O cache é limpo a cada teste (limites de taxa). Rotas de fases futuras são testadas por **sondas** em `apps/core/tests/probe_urls.py` (`@pytest.mark.urls`); quando a rota real nascer, troque a sonda por ela (a sonda de admin foi trocada pelas rotas reais na Fase 5).
- Produção exige cache compartilhado (`config/settings/prod.py` recusa `LocMemCache`; padrão `DatabaseCache`, criado por `manage.py createcachetable`, já no comando do serviço `api`).
- Limitação conhecida: o e-mail de redefinição é enviado de forma síncrona; o tempo de resposta pode diferir entre e-mail existente e inexistente (o corpo e o status são idênticos). Tratar com fila/envio assíncrono em BE-085 ou na Fase 7.
- Testes de modelos `managed=False` com `transaction=True` dependem da limpeza em `backend/conftest.py`.

**Módulos da Fase 3 (leia antes da Fase 4)**
- Rotas: cada app declara em `urls.py` os caminhos completos do contrato (ex.: `workshop/services/`) e todos são montados em `path('api/', include(...))` no `config/urls.py`. Rotas `/workshop/*` ficam espalhadas por `catalog`, `workshops`, `vehicles`, `attendances`, `reviews` e `promotions`.
- Camadas: `selectors.py` (leituras com `select_related`/`prefetch_related`/`Subquery`, número fixo de queries) → `serializers.py` (forma) → `services.py` (`@transactional`). Views só orquestram. Use `is_schema_generation(self)` (`apps/core/mixins.py`) em `get_queryset` que lê `request.user`, senão o `spectacular --fail-on-warn` quebra.
- Busca de texto: `apps/core/search.py` (`search_filter(qs, q, "campo", …)`): minúsculas, espaços colapsados e **sem acentos** (DP-19) por `translate()` — sem a extensão `unaccent`. Reaproveite no mapa (BE-067).
- Filtro `?status=a,b` em coluna ENUM: `CommaSeparatedChoiceFilter` (`apps/core/filters.py`) valida cada valor (400), senão um valor inválido vira erro de SQL.
- Horários com significado de ordem usam `ClockTimestamp()` (`apps/core/db.py`, `clock_timestamp()`), não `CURRENT_TIMESTAMP`: `MESSAGE.date_sent` (polling com `after` inclusivo não perde mensagem confirmada tarde) e `REVIEW.date_response`.
- Regras da **aplicação** acrescentadas onde o banco não cobre (documentadas nos serviços): (1) transição para o **mesmo** status → 409 (a trigger ignora UPDATE sem mudança; cancelar/enviar duas vezes passaria em silêncio); (2) orçamento e itens só mudam com o atendimento em `budgeted` — depois do envio o orçamento continua `pending` e a trigger deixaria editar (RB-08); (3) enviar orçamento vencido → 409; (4) o cliente só recusa orçamento já enviado (`waiting_approval`).
- `PATCH /workshop/attendances/{id}/` grava em `technical_notes` (DP-13); `observations` no corpo é aceito como **sinônimo** porque o frontend envia esse nome — o texto do pedido do cliente nunca é sobrescrito. A tela T19 ainda lê `a.observations` (ajuste em BE-072, registrado em `frontend/PENDENCIAS-API.md` §8).
- Respostas que o frontend lê de um jeito específico: item de orçamento = campos do item **no nível raiz** + `budget{id,status_budget,total_price}` (o `w-budget.js` lê `x.id`); `GET /chats/{id}/messages/` **sem** `after` devolve na página 1 as mensagens **mais recentes** (o `chat.js` só lê a página 1), sempre em ordem cronológica; favorito tem `id = id_workshop`; registro do histórico tem `id = "service-N" | "part-N"` e traz `workshop_name`.
- Nota média: `apps/reviews/selectors.py` (`rating_annotations(...)`, só `published`, DP-23); nome do autor abreviado: `apps/reviews/domain.py` (`author_display_name`, DP-15). Reaproveite em BE-065/066/067.
- Divulgação paga: preço = diárias (arredondadas para cima) × `SAM_ADVERTISING_PRICE_PER_DAY` (padrão 10,00; `backend/.env.example`). Nasce `pending/pending`; ativação/pagamento é BE-076.
- **Notificações (BE-070, feitas na Fase 4)** — ligadas em `request_attendance`, `cancel_attendance` (cliente → oficina), `respond_budget`, `send_budget`, `transition_attendance` (oficina → cliente, inclusive cancelamento e reabertura), `send_message`, `create_review` e `respond_review`. Ver a seção "Módulos da Fase 4".
- Testes: fixtures `ready_workshop`/`ready_workshop_session` (oficina com cadastro concluído) no `conftest.py`; fábricas `make_ready_workshop()`, `jpeg_upload()`, `fake_image_upload()`, `stored_name()` em `apps/core/tests/factories.py`; `Flow` em `apps/attendances/tests/conftest.py` leva um atendimento a qualquer estado (`flow.at("waiting")`…). Vigência temporal (NOW() do banco) se testa com `@pytest.mark.django_db(transaction=True)` e relógio real (ver `apps/promotions/tests`).
- PostgreSQL 18: violação de `RESTRICT` é SQLSTATE `23001` (mapeado → 409; o 16 usa `23503`). O `init.sql` aplica no 17+ desde a correção da P-21 (`public.clean_service_name` em `normalize_service_name()`).

**Módulos da Fase 4 (leia antes da Fase 5)**
- **Oficina pública (DP-20):** `apps/workshops/selectors.py` → `public_workshops()` (= `active` **e** ≥ 1 serviço não rejeitado) e `public_workshop_or_404(id)`. Use em toda leitura pública nova; oficina não pública some de perfil, mapa, vitrine e listas.
- **Aberto agora:** `apps/workshops/domain.py` → `business_clock()`/`is_open_at(hours)`; o mapa usa a mesma régua em SQL (`_open_now_exists`). Nos testes, controle o relógio com `monkeypatch.setattr("apps.workshops.domain.business_now", …)`. Sem horários → `null` (não `false`).
- **Mapa:** `apps/workshops/geo.py` (caixa envolvente com 1° = 2πR/360 + folga de 1%, e `HaversineKm` em SQL). Os UNIONs (mapa e vitrine) projetam colunas com prefixo (`m_*`, `p_*`) na mesma ordem nas duas metades; o serializer monta a resposta (`to_representation`). Um ponto vinculado a oficina só aparece como `workshop`, e só se ela for pública.
- **Vitrine:** `apps/promotions/selectors.py` → `on_air(workshop_id=None, include_advertisements=True)`. Item `advertisement` tem `id` da divulgação (alvo de denúncia) e `id_promotion`; `is_running_now` é `null` em `promotion`.
- **Notificações:** gere sempre por `apps/notifications/events.py` (textos pt-BR e destinos `.html` documentados na tabela do módulo); `notify()` grava só depois do commit e nunca derruba a operação (erro vai para `sam.notifications`). Chat: uma notificação não lida por conversa (`notify_chat_message`, trava o chat); ler a conversa a marca como lida. Eventos de moderação e de divulgação foram acrescentados na Fase 5 (ver abaixo).
- **Rotina de expiração:** `run_expiration_jobs` roda numa transação com `pg_advisory_xact_lock`, captura os orçamentos já enviados (`waiting_approval`) que vão vencer e notifica o cliente uma vez. Orçamento nunca enviado expira sem aviso.
- **Testes de notificação:** use `django_capture_on_commit_callbacks(execute=True)` (fixture `commit` em `apps/notifications/tests/test_notifications.py`) — sem isso os `on_commit` não rodam nos testes não transacionais.
- **Dev local:** o `backend/.env` desta máquina tem `SAM_TIME_ZONE=UTC`; DP-16 é `America/Sao_Paulo` (como no `.env.example`). Com UTC o "aberto agora" sai 3 h adiantado.

**Módulos da Fase 5 (leia antes da Fase 6)**
- **Moderação (`apps/moderation/`):** `services.py` (`moderate_denunciation`, `hide_review`, `approve_/reject_service_request`) → `serializers.py`/`filters.py` → `views.py`. Regras: resolução exige decisão (400); resolvida ou mesmo status → 409; `upheld` = avaliação `hidden` / promoção `inactive` (+ estorno das divulgações pagas) / divulgação `cancelled`. Aprovar/rejeitar chamam as funções SQL; solicitação = `WORKSHOP_SERVICE` com `status_solicitation` não nulo (serviço do catálogo → 404). Path param da denúncia é `id` (`lookup_url_kwarg`) para o OpenAPI não mostrar `{id_denunciation}` (P-22).
- **`db_errors`:** `unique_violation` **sem** nome de constraint (RAISE … `ERRCODE = 'unique_violation'` numa função) agora devolve 409 com a mensagem do banco em vez da genérica.
- **Django Admin (DP-03, ADR 0003):** `apps/{accounts,catalog,workshops,promotions}/admin.py`. Contas sem incluir/excluir; `password_hash` fora do formulário; salvar grava **só os campos alterados**; status por ação ou formulário, sempre via `accounts.services.set_account_status` e auditado (`sam.audit` + `LogEntry`). Serviço e categoria sem excluir (desative com `active`); nome do serviço validado como no banco. Pontos com as regras do banco no formulário. Divulgações: só leitura + ações.
- **Divulgação paga (BE-076, ADR 0009):** `apps/promotions/services.py` → `confirm_advertisement_payment`, `mark_advertisement_payment_failed`, `cancel_advertisement`, `activate_due_advertisements`, `refund_cancelled_advertisements`. A rotina `run_expiration_jobs` agora também ativa as pagas (`divulgações ativadas`) e marca estornos (`estornos marcados`), na mesma transação com advisory lock, depois das expirações. **Trave a promoção com `select_for_update(no_key=True)`** (FOR NO KEY UPDATE): `FOR UPDATE` conflita com o `FOR KEY SHARE` da trigger da divulgação e cria deadlock com a ativação.
- **Contas (BE-078, ADR 0018):** `accounts.services.anonymize_account(role, id)` (irreversível; nome "Anônimo", e-mail `anonimo-<perfil>-<id>@anonimizado.invalid`, senha inutilizável, fotos apagadas após o commit, favoritos/notificações apagados; histórico fica) e `is_anonymized()`; conta anonimizada não volta a `active` (409 no serviço, erro no formulário).
- **Manutenção preventiva (BE-077, ADR 0005):** `apps/vehicles/reminders.py` → `upcoming_maintenance(execuções, km atual)` é **pura** (teste sem banco); `vehicle_upcoming(veículo)` para a API e `send_due_reminders()` para a rotina. Item = `id_service` ou nome normalizado; intervalo = o mais recente do item; limiar `SAM_MAINTENANCE_REMINDER_PERCENT` (padrão 10). "Não repetir" = `MAINTENANCE_REMINDER.id_register_maintenance` UNIQUE + `INSERT … ON CONFLICT DO NOTHING` (só quem inseriu notifica). O histórico continua só-inclusão. `run_expiration_jobs --loop --reminders-interval N` chama os lembretes no máximo a cada N s (0 desliga); o modo de uma execução só não os envia. Schema agora tem **24 tabelas** (23 do `init.sql` + `maintenance_reminder`).
- **Testes:** `staff`/`staff_client`/`commit` em `apps/moderation/tests/conftest.py`; Django Admin testado com `django.test.Client` logado como superusuário (ações = POST na changelist com `action` e `_selected_action`). Ativação de divulgação depende do `NOW()` do banco: testes com `transaction=True` e relógio real (`apps/promotions/tests/test_advertisement_payment.py`).

**Módulos da Fase 6 (leia antes da Fase 7)**
- **Mundo de teste** (`apps/core/tests/world.py`): `build_world()` cria os lados A e B (cliente, oficina pronta, veículo com histórico, atendimentos em vários estados, chat, notificações, promoção com divulgação, denúncia…) com o marcador `SEGREDO-<lado>` nos campos privados; `grow_side()` multiplica os dados (teste de N+1). Reaproveite em testes novos.
- **Rota nova** entra sozinha na matriz de autorização (401/403), no detector de N+1 e no fuzz de parâmetros; precisa de: linha em `CONTRACT` (`tests/security/test_authz_matrix.py`), parâmetro de caminho no padrão `id_<entidade>` (ou `{id}` sob segmento conhecido) e um passo 2xx no fluxo de `tests/contract/test_contract.py`. Lista de verificação: `backend/docs/seguranca/checklist-endpoints.md`.
- **Campo omitido de propósito** numa resposta (ex.: só o interlocutor no chat): decore o serializer com `@optional_response_fields(...)` (`apps/core/openapi.py`); `APIView` que pagina à mão documenta a resposta com `paginated(Serializer, "Nome")`.
- **Limites** de texto, senha e busca ficam em `apps/core/limits.py` (= `maxlength` da tela, DP-19); a busca usa `search_filter`, que já valida NUL e tamanho. Corpo acima de 1 MB (JSON) ou 16 MB (multipart) → 413 antes da view.
- **SQL**: nada de `raw()`/`extra()`/`RawSQL` nem SQL interpolado; exceção consciente leva `# sql-safe: <motivo>` numa das linhas da chamada (`tests/security/test_sql_safety.py` + ruff `S608`).
- **Regra da aplicação nova**: responder (aprovar/recusar) um orçamento já respondido com o mesmo status → 409 (antes dava 200 e notificava de novo).
- **Produção**: `ALLOWED_HOSTS` obrigatório; atrás do Nginx ligue `USE_X_FORWARDED_PROTO=True` (senão laço de redirecionamento); `/api/health/` fica fora do redirecionamento HTTPS; `SAM_EMAIL_ASYNC=True` por padrão em produção.
- **E2E**: a API roda no `live_server` (banco de teste) e o frontend real é servido com `config.js` reescrito; `DJANGO_ALLOW_ASYNC_UNSAFE` só existe enquanto o navegador está aberto (se vazar, o `check --deploy` acusa `async.E001`).
- **Banco local**: o PostgreSQL 18 desta máquina aplica o `init.sql` sem ajuste desde a P-21; para não tocar o banco de dev, use um cluster descartável (`initdb` + `pg_ctl` numa porta livre, ex. 55432).

**Módulos da Fase 7 (leia antes de mexer na implantação)**
- **Imagens**: um só `backend/Dockerfile`, contexto = **raiz** (lê `database/init.sql`, `frontend/`, `deploy/nginx/`). Alvo `api` (padrão; Gunicorn como PID 1, usuário 10001) e `proxy` (Nginx com o frontend, `config.prod.js` e os estáticos do `collectstatic`). O `.dockerignore` da raiz exclui `**/.env`, `**/venv`, segredos e testes. Backup: `deploy/backup/Dockerfile` (`postgres:16` — mesma versão do `db`).
- **Produção = mesma origem** (ADR 0021): `config.prod.js` com `API_BASE = window.location.origin`; CORS vazio; `CSRF_TRUSTED_ORIGINS=https://<domínio>`. Origem externa nova no frontend exige mudar `deploy/nginx/snippets/csp-frontend.conf` (o E2E `test_same_origin_csp.py` lê a CSP de lá).
- **IP do cliente**: `SAM_NUM_PROXIES` = 0 sem proxy (padrão) e 1 atrás do Nginx, que reescreve `X-Forwarded-For`. Nunca deixe `None` (o DRF passa a confiar no cabeçalho do cliente). Use `apps.core.throttles.client_ip()`.
- **Batimento das rotinas**: `apps/core/heartbeat.py` (`record_success` na transação da rotina, `record_failure` em transação própria, `job_status` pelo relógio do banco). Rotina nova = nome novo em `SAM_HEARTBEAT_MAX_AGE` + `JOB_LABELS` do monitor.
- **Monitor**: `apps/core/monitoring.py`; teste com `Monitor(config, clock=…, notifier=Recorder())`. Indisponibilidade só alerta depois de `FAILURES_BEFORE_ALERT` falhas; testes que simulam banco fora precisam de `transaction=True` (o monitor fecha a conexão quebrada).
- **Schema**: `manage.py check_schema` (roda no `deploy.sh`) e `manage.py schema_diagram` (regenera `docs/DIAGRAMA_SAM.svg`; um teste compara). Mudou o schema? Rode o `schema_diagram` com o banco migrado.
- **Implantação**: `deploy/deploy.sh` nunca troca a versão no ar antes de `migrate` + `check_schema` passarem; migrations precisam ser compatíveis com a versão anterior (`backend/docs/migrations.md`). Comandos manuais: `deploy/compose.sh`. Testes do script: `tests/deploy/test_deploy_script.py` (docker falso).
- **Pool**: `CONN_HEALTH_CHECKS` ligado (`DB_POOL_CHECK`): a conexão é testada ao sair do pool (sobrevive a reinício do banco). As settings de teste não usam pool.

**BE-094 (leia antes de mexer no mapa, backup ou staging)**
- **Mapa, duas fontes**: `/map/points/` (SAM) e `/map/external-points/` (OpenStreetMap pela Overpass, `apps/workshops/overpass.py`). A segunda responde **sempre 200** com `status`; nunca deixe uma falha externa virar 5xx. Testes não falam com a Overpass pública: `FakeOverpass` (`apps/workshops/tests/test_overpass.py`), URL vazia em `config/settings/test.py`.
- **Rota com parâmetro obrigatório na query string** → acrescente em `QUERY` de `tests/perf/test_query_counts.py`.
- **Função SQL usada em índice/constraint** chama outras funções **com schema** (`public.f(...)`): o `pg_restore` roda com `search_path` vazio (defeito da `catalog/0002`).
- **Volume nomeado montado por mais de um serviço**: só o dono monta com cópia; os demais `read_only` + `nocopy` (o Docker copia o dono do ponto de montagem da imagem para o volume vazio).
- **`compose.prod.yml` exige `SAM_VERSION` em toda chamada**: no `deploy.sh`, use `compose_v` (o `docker` falso dos testes reproduz isso).
- **Backup**: o agendador roda se não houve sucesso desde a última ocorrência de `BACKUP_HOUR`; o manifesto traz contagem e md5 por tabela, conferidos pelo `sam-restore`.
- **Staging local**: `deploy/staging/staging.sh` (projeto `sam-staging`, segredos em `~/.local/share/sam-staging`); `docker` nesta máquina pode exigir `newgrp docker`.

**Frontend**
- `frontend/js/api.js` é o contrato real: 401 → redireciona para o login; 403 → `404.html?code=403` (exceto chamadas `soft`/`quiet`). O primeiro POST faz `GET /auth/me/` para obter o cookie `csrftoken`.
- Não altere o frontend sem necessidade; divergências de contrato são resolvidas em BE-072 e registradas em `frontend/PENDENCIAS-API.md`.

---

## 7. Registro de sessões

Acrescente uma linha por sessão (mais recente embaixo). É o que permite ao próximo chat continuar sem perder contexto.

| Data | Fase | O que foi feito | Verificação | Pendências deixadas |
|---|---|---|---|---|
| 2026-11-04 → 2026-11-14 | 0–1 | Esqueleto, configuração, dependências, compose, schema, modelos, erros, logs, health, OpenAPI, imagens, utilitários, jobs. | pytest verde | ADRs (P-12). |
| até 2026-11-16 | 2 (parcial) | Auth de 2 perfis, cadastro, login, me/logout, senha (Argon2), redefinição, CORS, throttles, permissões base; início de BE-036/BE-041; CNPJ alfanumérico (back e front). Não commitado. | 203 testes verdes; ruff com 25 erros | P-01…P-11. |
| 2026-11-17 | Auditoria | `AUDITORIA.md` e este `README.md` criados. Nenhum código alterado. | 203 testes verdes; ruff falha; migrations OK | Fechar a Fase 2 (seção 4.3). |
| 2026-11-17 | 2 (fechamento) | P-01…P-04, P-06…P-11, P-15, P-19: 401 com `WWW-Authenticate`; sessão com *fingerprint* da senha (troca/redefinição derrubam outras sessões); `flush` + `rotate_token` no login; `PATCH /me/` com `ImageURLField`/`apply_image_changes`; serviços de conta com `@transactional` e erros do banco por campo; redefinição/troca → 204; bloqueio progressivo de login, throttles de mensagem/polling, 429 em português, cache compartilhado obrigatório em produção; permissões com mensagens, `IsAccountHolder`, `WORKSHOP_PERMISSIONS`; `AdminViewMixin` + auditoria; `/api/admin/` montado; CSRF em JSON; 142 testes novos. BE-028/030/031/033/035 marcadas. | 345 testes verdes; ruff, makemigrations, check e spectacular OK | PR do branch `feat/fase-2-autenticacao` para `main`; acabamentos das Fases 0–1 (P-12, P-13, P-14, P-16, P-17, P-18, P-20). |
| 2026-11-17 | 3 | BE-036…BE-064 (29 tarefas, 60 endpoints): catálogo global com busca sem acentos; oficina (conta, página, horários atômicos, ponto no mapa, serviços, produtos); veículos com fotos por posição e histórico só-inclusão (registro → 405 em PATCH/DELETE); atendimento, orçamento, itens, envio, execução, transições e entrega com histórico; clientes atendidos e histórico autorizado; chat (abrir idempotente e concorrente, polling com `after` inclusivo e `clock_timestamp`, entregue/lida, limites de taxa); avaliações, resposta, denúncias, favoritos; promoções com vigência efetiva e divulgação paga. P-14 (rotas) resolvida; `23001` (PG 18) mapeado; sonda de `/workshop/attendances/` trocada pela rota real. 298 testes novos. | 643 testes verdes; ruff, makemigrations, check e spectacular OK (PostgreSQL 18 local com `init.sql` corrigido por P-21; ver seção 1) | P-21 (init.sql × PG 17+); notificações dos eventos (BE-070); divergências de contrato para BE-072 (`frontend/PENDENCIAS-API.md` §8); acabamentos das Fases 0–1 (P-12, P-13, P-16, P-17, P-18, P-20); commit/PR da Fase 3. |
| 2026-11-17 | 4 | BE-065…BE-072: perfil público com `is_open_now`/`is_favorite` e sem dados privados; produtos, promoções vigentes e avaliações publicadas por oficina; mapa (UNION oficinas + POIs, busca sem acentos inclusive por serviço, categoria por id ou nome, tipo, aberto agora, caixa envolvente + Haversine, raio ≤ 100 km); vitrine `/promotions/` (divulgações no ar + promoções vigentes de oficinas públicas); API de notificações; geração por eventos (`on_commit`, agrupamento do chat, leitura do chat lê a notificação, orçamento expirado pela rotina com advisory lock); `import_pois` (CSV/GeoJSON idempotente, `--dry-run`, relatório). BE-072: carga por API num banco descartável e percurso de 34 telas/estados no Chromium headless (visitante, cliente, oficina, oficina no assistente) sem "servidor indisponível" nem erro de API/console; corrigidos T19 (`technical_notes` via normalizador do `api.js`) e a credencial demo visível com `DRIVER:'http'` (`.demo[hidden]` em `auth.css`). Defeito achado pelos testes: caixa do mapa menor que o círculo (111,32 km/°) cortava pontos na borda. 123 testes novos. | 766 testes verdes; ruff, makemigrations, check e spectacular OK (PostgreSQL 16) | P-22 (nomes de parâmetro no OpenAPI); P-21; acabamentos das Fases 0–1 (P-12, P-13, P-16, P-17, P-18, P-20); `SAM_TIME_ZONE=UTC` no `.env` local; commit/PR da Fase 4 (a Fase 3 já está no `main`, commit `f2cb528`). |
| 2026-11-17 | 5 | BE-073…BE-076 e BE-078 (BE-077 fora: *Could have* não pedido). Moderação: fila de denúncias com denunciante e resumo do conteúdo, `PATCH` com efeito de `upheld` (avaliação oculta, promoção desativada com estorno das divulgações pagas, divulgação cancelada), ocultar avaliação, notificações ao denunciante e à oficina, auditoria com transição; solicitações de serviço personalizado (fila, aprovar reaproveitando nome normalizado — provado com threads —, rejeitar com motivo). Django Admin de contas (bloquear/ativar/desativar auditados, só campos alterados), catálogo, pontos e divulgações (confirmar pagamento, não identificado, cancelar). BE-076: ativação e estorno na rotina `jobs`; desativar promoção marca estorno; promoção travada com `FOR NO KEY UPDATE` (evita deadlock com a ativação). BE-078: anonimização irreversível com confirmação. ADRs 0003/0009/0015/0018 + índice. Sonda de admin trocada pelas rotas reais; `db_errors` usa a mensagem de `unique_violation` sem constraint. `PENDENCIAS-API.md` atualizado. 95 testes novos. | 861 testes verdes; ruff, makemigrations, check e spectacular OK (PostgreSQL 18 descartável com `init.sql` corrigido por P-21) | P-12 (19 ADRs restantes); P-22; P-21; acabamentos das Fases 0–1 (P-13, P-16, P-17, P-18, P-20); `SAM_TIME_ZONE=UTC` no `.env` local; commit/PR da Fase 5; telas T27/T28 (fora do backend). |
| 2026-11-17 | 5 (BE-077) | A pedido do responsável: próximas manutenções e lembretes de manutenção preventiva. Cálculo puro em `apps/vehicles/reminders.py` (item por serviço do catálogo ou nome normalizado, última execução manual ou da oficina, intervalo mais recente, `ok`/`soon`/`overdue` com limiar configurável); `GET /vehicles/{id}/upcoming-maintenance/`; tabela `MAINTENANCE_REMINDER` (`vehicles/0004`, ida e volta testada) e `send_maintenance_reminders` (um aviso por ciclo, concorrência testada), agendado no `jobs` a cada hora; evento `maintenance_due` no sino. Frontend T12: seção "Próximas manutenções" e campo de intervalo funcionando com `DRIVER:'http'` (`api.vehicles.upcoming`), verificado no Chromium headless. ADR 0005; `PENDENCIAS-API.md` P3 resolvida. 28 testes novos. | 889 testes verdes; ruff, makemigrations, check, spectacular e `node --check` OK (PostgreSQL 18 descartável) | Aviso à oficina (opcional no backlog 2.3) e intervalo por tempo não feitos (ADR 0005); demais pendências como na linha anterior. |
| 2026-11-17 → 2026-11-18 | 6 | BE-079…BE-087 + P-13, P-16, P-20, P-22. **Autorização:** matriz gerada do schema (89 operações; 401/403/404, vazamento de campos privados, mass assignment, colisão de ids entre perfis, Django Admin) — mutação proposital reprovada. **Banco:** suíte `db_rules` (269 casos, positivo e negativo de cada trigger/função). **Concorrência:** 6 cenários repetidos + deadlock real. **Contrato:** 89 operações validadas em modo estrito + normalizadores do `api.js` no Node; schema corrigido (`user`, `total_price`, horários paginados, chat com só o interlocutor) e P-22. **E2E:** F1–F8 + 2 cenários de falha no Chromium. **Desempenho:** sem N+1, sem `Seq Scan` com volume, carga de polling (200 usuários: p95 11,5 ms; ADR 0023). **Produção:** `check --deploy` sem avisos, HSTS/COOP/Referrer-Policy, `ALLOWED_HOSTS` obrigatório, e-mail de redefinição assíncrono. **Entradas:** `limits.py`, 413, NUL, fuzz, proibição de SQL interpolado. **CI:** cobertura (98%), pip-audit, gitleaks, E2E, pre-commit. **Defeitos corrigidos:** `?q=%00` → 500 (serviços e pontos de interesse); `?after=` com data impossível → 500 (chat); JSON > 2,5 MB → 500; aprovar/recusar o mesmo orçamento duas vezes → 200 com notificação repetida; histórico manual aceitava 1000 caracteres (tela: 200). 951 testes novos + 10 E2E. | 1840 testes verdes + 10 E2E; ruff, makemigrations, check, `check --deploy`, spectacular e pip-audit OK (PostgreSQL 18 descartável com `init.sql` corrigido por P-21) | P-23 (formatação geral, decisão do responsável); P-12 (18 ADRs); P-17, P-18, P-21; repetir a carga em staging (BE-094); Firefox/WebKit no E2E não configurados; commit/PR da Fase 6. |
| 2026-11-18 | 7 | BE-088…BE-093 implementadas + P-12, P-17, P-18; BE-094 preparada. **Imagem** multi-estágio (API sem root, Gunicorn gthread com encerramento controlado, healthcheck com o `Host` certo) e **proxy** Nginx (TLS 1.2/1.3, HTTP→HTTPS, HSTS, CSP do frontend e da API, mídia só de imagens, 413 em JSON, `X-Forwarded-*`, logs JSON sem query string, mesma origem com `config.prod.js`). **Backup/restauração** cifrados (GPG), manifesto com contagens no mesmo snapshot do dump, rclone, retenção, agendador e alerta. **Implantação** (`compose.prod.yml`, `deploy.sh` com volta automática, `check_schema`, `compose.sh`). **Monitor** (API, banco, conexões, deadlocks, locks, batimentos, 5xx/p95, disco; webhook/e-mail/ping) + `GET /api/health/jobs/` + tabela `JOB_HEARTBEAT`. Pool com verificação de conexão. RUNBOOK, migrations.md, 17 ADRs, ACEITE.md, diagrama gerado do banco (original em `docs/historico/`), docs do frontend e `backlog.md`. CI: cliente PostgreSQL 16 + job `deploy-smoke`. **Defeito corrigido:** sem `NUM_PROXIES` o DRF usava o `X-Forwarded-For` enviado pelo cliente (limites de login/cadastro por IP contornáveis); atrás do Nginx todos dividiriam o IP do proxy. 98 testes novos (90 na suíte padrão + 8 do ensaio de backup) + 2 E2E. | 1930 testes verdes + 12 E2E; `-m deploy` 46/46 no PostgreSQL 18 descartável (ensaio de backup); cobertura 97%; ruff, makemigrations, check, `check --deploy`, spectacular e pip-audit OK (PostgreSQL 16 do compose) | **`deploy/smoke-test.sh` não executado** (sem acesso ao Docker nesta máquina): build das imagens e subida real só no job `deploy-smoke`; BE-094 (staging, decisões de tiles/pontos/RPO-RTO/Firefox-WebKit, assinatura); P-21, P-23; Fase 7 não commitada (pedido do responsável). |
| 2026-11-18 | 7 (BE-094) | Decisões do responsável implementadas e validadas. **Mapa:** tiles do OSM com `referrerPolicy` (a política do OSM exige Referer; a página usa `same-origin`) e provedor configurável (`MAP_TILES`); `GET /map/external-points/` (Overpass: células de 0,05° com cache de 24 h, orçamento por minuto, recuo exponencial, tempo limite, sempre 200 com `status`, duplicatas com o SAM removidas, ODbL); camada no `map.js` (losangos, popup sem funções do SAM, legenda, filtros, liga/desliga, aviso de falha). **Backup:** md5 do conteúdo por tabela no manifesto e na restauração; agendador diário com recuperação de atraso. **Staging local** `https://sam.localhost` (`deploy/staging/`: CA local com `nameConstraints`, só loopback, dados de demonstração pela API, `check`, `restore-drill`, `overpass`). **E2E** parametrizado em Chromium e Firefox; Playwright 1.41 → 1.65.2. **Defeitos achados pela subida real e corrigidos:** `deploy.sh` sem `SAM_VERSION` no `db_psql` (primeira implantação parava); volume de mídia virava root (todo upload dava 500); **nenhum backup era restaurável** (`normalize_service_name` sem schema × `search_path` vazio do `pg_restore` → migration `catalog/0002`); agendador do backup derivava para 26 h; aviso "nenhum estabelecimento" antes da resposta. ADRs 0024–0026, `STAGING.md`, `RELATORIO-BE-094.md`, `ACEITE.md`. | 1992 testes + 51 `-m deploy` + 29 E2E (Chromium e Firefox) + 12 do staging; cobertura 97,22 %; `smoke-test.sh` 42/42; `restore-drill` 5,6 s; ruff, makemigrations, check, `check --deploy`, spectacular e pip-audit OK | Assinatura do aceite; runbook por outra pessoa; roteiro manual das 26 telas; observar o backup diário por alguns dias; carga de polling com Nginx; P-21, P-23; a Overpass pública `overpass-api.de` estava sem capacidade (staging usa `maps.mail.ru`); nada commitado nesta sessão (commit só com autorização). |
| 2026-11-18 | 7 (P-21, P-23) | Decisões do responsável. **P-23:** auditoria do Git (árvore limpa; o BE-094 já estava no `8c72a9a`, nada funcional a separar); `ruff format .` em commit exclusivo **`483a446`** (135 arquivos, AST idêntico nos 281 `.py`, suíte igual à de antes: 1992 + 9 pulados); commit **`54e9bb1`** com `.git-blame-ignore-revs`, CI com `ruff format --check .` bloqueante (sem `continue-on-error`), pre-commit e docs. **P-21:** `init.sql` com `public.clean_service_name` em `normalize_service_name()` (função preservada, `core/0001` intacta); defeito reproduzido antes no PG 18.6 (`function clean_service_name(text) does not exist`, 0 tabelas) e ausente no 16; depois, banco vazio por `psql -f` e por `migrate` no 16.15 e no 18.6 (contagens do BE-007, `check_schema`, índices com `search_path` restrito/vazio, 23505, dump/restore no 18); teste `apps/catalog/tests/test_init_sql_search_path.py` (3 casos, reprova com o arquivo antigo). 23001 → 409 preservado (RESTRICT: 23503 no 16, 23001 no 18). | PG 16: 1995 passaram + 9 pulados (backup, `pg_dump` 18 × 16), cobertura 97,22 % / 98 %; PG 18: 2004 passaram; E2E 29/29; ruff, `ruff format --check`, makemigrations, check, `check --deploy`, spectacular OK | P-21 **não commitada** (aguarda autorização do commit funcional); `pip-audit` não repetido (dependências inalteradas); `git config blame.ignoreRevsFile .git-blame-ignore-revs` em cada clone; demais pendências do aceite inalteradas. |
