# SAM — Auditoria das Fases 0, 1 e 2 do backend

> **Data:** 17/11/2026 · **Branch:** `main` (HEAD `0c6bce9` + alterações não commitadas)
> **Referência:** `backlog/backlog_backend.md` (BE-001 a BE-035)
> **Escopo:** verificar se o que o backlog marca como concluído nas Fases 0–2 existe, funciona e atende aos critérios de aceitação.
> **Nenhum arquivo do projeto foi alterado por esta auditoria.** Foram criados só este arquivo e o `README.md` (que estava apagado na árvore de trabalho e vazio no HEAD).

> **Atualização (17/11/2026, fechamento da Fase 2):** as pendências P-01, P-02, P-03, P-04, P-06, P-07, P-08, P-09, P-10, P-11, P-15 e P-19 foram resolvidas e testadas; P-14 e P-16 foram feitas em parte. O estado atual está no `README.md` (seções 3, 4.3 e 7). **Fase 3 (17/11/2026):** P-14 resolvida (rotas por app montadas em `api/`); achada a P-21 (`init.sql` × PostgreSQL 17+), registrada no README. O restante deste documento descreve o projeto **no momento da auditoria**.

---

## 1. Resumo executivo

| Fase | Tarefas | Marcadas `[x]` no backlog | Resultado da auditoria |
|---|---:|---:|---|
| 0 — Preparação e arquitetura | 5 | 5 | **Concluída na prática**, com 1 pendência documental (ADRs de BE-001 não existem em arquivo) e ajustes menores. |
| 1 — Banco e infraestrutura | 18 | 18 | **Concluída.** Schema, modelos, erros, logs, health, OpenAPI, mídia, utilitários e job estão implementados e testados. Faltam alguns testes previstos nos critérios (paginação/filtro CSV, EXPLAIN, `pg_dump`). |
| 2 — Autenticação e autorização | 12 | 7 | **Parcial.** 7 marcadas como concluídas (BE-024/025/026/027/029/032/034), mas há defeitos em duas delas (BE-025: visitante recebe 403 em vez de 401; BE-032: sem testes). As 5 desmarcadas (BE-028/030/031/033/035) estão **parcialmente** implementadas. |

**Números verificados nesta auditoria**

| Verificação | Resultado |
|---|---|
| `pytest` (PostgreSQL 16 real, `config.settings.test`) | **203 testes passaram**, 0 falhas (6,3 s) |
| `manage.py makemigrations --check --dry-run` | **Sem alterações pendentes** |
| `manage.py check --database default` | OK (coberto pelos testes) |
| `spectacular --validate --fail-on-warn` | OK (coberto por teste) |
| `ruff check .` | **FALHA — 25 erros** (19 `I001` imports desordenados, 2 `F401` imports sem uso, 6 `B904` `raise` sem `from`). Todos em código da Fase 2 e no `catalog`. **O workflow `Backend Tests` do CI quebra no passo "Lint".** |
| Estado do git | 34 caminhos alterados/não rastreados: quase toda a Fase 2 **não está commitada**. |

**Conclusão:** as Fases 0 e 1 podem ser consideradas entregues. A Fase 2 **não** está concluída: antes de iniciar a Fase 3 é preciso fechar as pendências da seção 6 (lista P-01 a P-20), começando pelas bloqueadoras (P-01 a P-06).

---

## 2. Método

1. Leitura das seções 1–9 e 14–17 do `backlog/backlog_backend.md` (índice, todas as tarefas BE-001…BE-035 na íntegra, decisões DP-01…DP-23, critérios de conclusão) e do estado dos checkboxes de BE-001…BE-094.
2. Leitura integral de **todo o código do backend**: `config/` (settings base/dev/prod/test, urls, wsgi/asgi), `conftest.py`, `pyproject.toml`, `requirements/`, `Dockerfile.dev`, `.env.example`, os 11 apps (`models`, `serializers`, `services`, `views`, `urls`, `migrations`, `templates`, `management`) e **todos os testes** (`apps/core/tests/*`, `apps/accounts/tests/*`, `tests/test_settings.py`).
3. Leitura da infraestrutura da raiz: `docker-compose.yaml`, `.env.example`, `.gitignore`, `.dockerignore`, `setup.sh`, `.github/workflows/*.yml`.
4. Frontend: leitura das mudanças não commitadas (`register.html`, `register.js`, `components-parts.js`), de `config.js`, de `api.js` (camada HTTP, CSRF, tratamento de 401/403, rotas consumidas), de `login.html`/`login.js`, de `frontend/README.md` e `frontend/CLAUDE.md`. As demais telas foram consideradas pelo contrato de `api.js` (é a única porta de dados).
5. `database/init.sql`: cabeçalho e convenções lidos; o conteúdo é verificado pelos testes que contam objetos após `migrate` (23 tabelas, 3 views, 16 triggers, 26 funções, 62 serviços, 11 categorias) e comparam colunas modelo × banco.
6. **Execução**: ruff, checagem de migrations, suíte completa e um teste de sondagem descartável (fora do repositório) para confirmar comportamentos HTTP da Fase 2 (resultados na seção 5).

Limites: o frontend não foi aberto em navegador; o Docker não pôde ser executado nesta máquina (sem permissão no socket), então a subida do `docker compose` foi avaliada por leitura.

---

## 3. Fase 0 — Preparação e arquitetura

| Tarefa | Backlog | Auditoria | Evidência e observações |
|---|:-:|:-:|---|
| **BE-001** ADRs | [x] | ⚠️ **Decisões tomadas, artefato ausente** | Não existe `backend/docs/adr/` nem nenhum ADR no repositório. **Decisão registrada pelo responsável: em BE-001 todas as decisões foram as recomendações sugeridas no backlog (seção 15, "Recomendação assumida")** — DP-01, DP-02, DP-03, DP-04, DP-05, DP-06, DP-16 e DP-21 (e, por consequência, as demais DPs seguem a recomendação padrão). O código é coerente com elas (init.sql como fonte + `managed=False`; sessão + CSRF com `Principal`; admin por `is_staff`; mídia em sistema de arquivos; `mileage_km`/`history_shared`; `setup_complete` = ≥1 serviço; `America/Sao_Paulo`; API 8000 / frontend 5500). **Pendência:** materializar os ADRs (ver P-12). |
| **BE-002** Esqueleto Django | [x] | ✅ (com ressalvas) | `manage.py`, `config/settings/{base,dev,prod,test}.py`, 11 apps registrados, DRF/django-filter/spectacular/corsheaders instalados, `GET /api/` → 404 JSON (testado). Ressalvas: (a) `config/urls.py:43` e `:47` incluem `apps.catalog.urls` **duas vezes** (`/api/services/` e `/api/catalog/services/`); (b) prefixos montados para apps futuros não batem com o contrato da seção 8 (`api/chat/` × `/chats/`, `api/moderation/` × `/admin/`, `api/core/` e `api/catalog/` não existem no contrato); (c) as pastas `tests/` dos apps estão vazias e, por isso, não vão para o git. |
| **BE-003** Variáveis de ambiente | [x] | ✅ | `django-environ`; `.env.example` raiz e `backend/.env.example` sem segredos; `.env` no `.gitignore` (confirmado: só os `.example` são rastreados). `prod.py` aborta com `SECRET_KEY` ausente/fraca/de exemplo, `DEBUG=True`, `DATABASE_URL` vazio ou `CORS_ALLOW_ALL_ORIGINS` (7 testes em `tests/test_settings.py`). Faltam: varredura de segredos no CI (critério da tarefa) e documentar no `.env.example` `FRONTEND_BASE_URL`, `THROTTLE_*`, `CACHE_*`. |
| **BE-004** Dependências | [x] | ✅ | `requirements/base.txt` (versões exatas, `psycopg[binary,pool]`, `django-environ`, `argon2-cffi`) e `dev.txt` (pytest, pytest-django, factory-boy, pytest-cov, ruff, pip-audit, playwright). Workflow `backend-dependencies.yml` com `pip install --dry-run` e `pip-audit`. |
| **BE-005** Docker Compose dev | [x] | ✅ (por leitura) | `docker-compose.yaml`: `db` (postgres:16 + healthcheck + volume `pgdata`), `api` (migrate + runserver 8000, volume de mídia), `jobs` (expiração em loop de 60 s), `web` (frontend em 5500). init.sql **não** é montado no `initdb` (correto). Ressalvas: `setup.sh` ainda diz "TO TERMINADO DE CONFIGURAR" e só cria `backend/.env` (o `.env` da raiz com `POSTGRES_PASSWORD` é obrigatório); `api` não tem healthcheck no compose. |

---

## 4. Fase 1 — Banco de dados e infraestrutura

| Tarefa | Backlog | Auditoria | Evidência e observações |
|---|:-:|:-:|---|
| **BE-006** Conexão, pool, transações | [x] | ✅ | Pool psycopg por variável, `ATOMIC_REQUESTS=False`, `USE_TZ=True`, check `sam.E002` para PostgreSQL < 13 (`apps/core/checks.py`) — testados. Falta o teste de 50 requisições simultâneas × limite do pool. |
| **BE-007** init.sql via migration | [x] | ✅ | `core/migrations/0001_init_schema.py`: não atômica, executa o arquivo com a conexão bruta, idempotente (sonda o schema), recusa schema parcial. Teste confirma 23/3/16/26/62/11. Não há teste de `pg_dump` (migrate × psql) nem documento da convenção de migrations futuras (a pasta `apps/core/sql/` proposta não foi criada; a convenção está só no docstring). A 0001 é irreversível por desenho. |
| **BE-008** `mileage_km` e `history_shared` | [x] | ✅ | `vehicles/0002`, com CHECK e reverso; testado. |
| **BE-009** Chat único por par | [x] | ✅ | `chat/0002` consolida duplicatas preservando mensagens e cria `uq_chat_client_workshop`; testado com dados duplicados. |
| **BE-010** `NOTIFICATION.url` | [x] | ✅ | `notifications/0002` com CHECK por regex; testado (`http://evil.com` recusado). |
| **BE-011** Índices | [x] | ✅ | `core/0002_perf_indexes.py` (nome difere do proposto `0003`, sem impacto). Sem teste de `EXPLAIN` (fica para BE-083). |
| **BE-012** (Cond.) `technical_notes` | [x] | ✅ | DP-13 seguiu a recomendação (adicionar). `attendances/0002`; testado. |
| **BE-013** (Cond.) `interval_km` | [x] | ✅ | `vehicles/0003` com recriação da view (ida e volta); testado. Obs.: a recomendação de DP-05 era adicionar `interval_km` "só se o aviso preventivo for adiante"; a coluna foi criada mesmo assim (opcional, sem impacto). |
| **BE-014** Modelos `managed=False` | [x] | ✅ | 26 modelos (23 tabelas + 3 views); teste compara colunas modelo × banco para cada um; colunas geradas como `GeneratedField`; `total_price` rejeitado na escrita manual (testado); round-trip por fábrica. |
| **BE-015** Testes com banco real | [x] | ✅ | `pyproject.toml` (pytest), `conftest.py` com `api_client`, `client_session`, `workshop_session`, `admin_session`, limpeza de tabelas não gerenciadas em testes transacionais, fábricas para todas as entidades, marcadores `db_rules`/`slow`. |
| **BE-016** Base da API | [x] | ⚠️ **Implementada, sem testes** | `SamPagination` (20/100, links relativos `?page=`), `SamModelSerializer` (sempre `id`), `CommaSeparatedFilter`, `SamJSONRenderer` (Decimal como string), permissão padrão `IsAuthenticated`. **Nenhum teste** de paginação, serializador base ou filtro CSV (exigidos pela tarefa). `SamModelSerializer` ainda não é usado (os serializers do `catalog` declaram `id` à mão). |
| **BE-017** Erros e SQLSTATE | [x] | ✅ | `db_errors.py` (23505/23503/23514/P0001/23502/22xxx/40P01/40001), `exceptions.py` (500 genérico, listas → `non_field_errors`, `Retry-After` no 503), `@transactional(retries=3)`; 15 testes. Obs.: `CHECK` com nome de constraint fora do mapa vira **400** genérico (a tabela 7.5 diz 409) — decisão aceitável, mas deve ser documentada. |
| **BE-018** Logging estruturado | [x] | ✅ | `RequestIDMiddleware`, JSON com `request_id`/usuário, mascaramento por chave e por conteúdo, `log_auth_event` com e-mail mascarado; testado. |
| **BE-019** Health checks | [x] | ✅ | `/api/health/` (0 queries) e `/api/health/ready/` (versão + schema, 503 se indisponível); testado. |
| **BE-020** OpenAPI | [x] | ✅ | `/api/schema/` e `/api/docs/` (abertos em DEBUG, `IsAdminUser` em prod); schema valida sem warnings (testado). O teste "rotas do schema × seção 8" só é possível quando as rotas existirem. |
| **BE-021** Imagens | [x] | ✅ | `images.py` (tipo por conteúdo, limite de bytes/dimensão, reencode sem EXIF, MPO→JPEG), `storage.py` (nome UUID, remoção pós-commit), `fields.py` (`ImageURLField`, `media_url` traduz `default-profile.png`); 13 testes. **Mas** o `PATCH /me/` da Fase 2 não usa esses componentes (ver P-02). |
| **BE-022** Utilitários de domínio | [x] | ✅ | CNPJ (inclui o **CNPJ alfanumérico** da RFB, com migration `accounts/0002`), placa, dinheiro `Decimal` (limites contra `1e1000`), nomes de serviço idênticos às funções SQL (testado contra o banco), `timeutils` no fuso do negócio. |
| **BE-023** Rotinas de expiração | [x] | ✅ | `manage.py run_expiration_jobs [--loop --interval]`, serviço `jobs` no compose; testes de expiração, idempotência e falha. |

---

## 5. Fase 2 — Autenticação e autorização

### 5.1 Situação por tarefa

| Tarefa | Backlog | Auditoria | Evidência e observações |
|---|:-:|:-:|---|
| **BE-024** Hash e política de senha | [x] | ✅ | Argon2 + PBKDF2 (rehash transparente testado com banco real), `passwords.validate_password` (≥8, letras e números, senha comum). |
| **BE-025** Autenticação de 2 perfis | [x] | ❌ **Com defeito** | `AccountSessionAuthentication` + `Principal` funcionam (sessão por perfil, `cycle_key` no login, CSRF em métodos não seguros, conta não ativa derruba a sessão). **Defeito:** a classe herda de `SessionAuthentication` sem `authenticate_header`, então o DRF converte "não autenticado" em **403** (confirmado: visitante em `/api/workshop/services/`, `/api/me/` e `/api/auth/logout/` recebe 403). O `api.js` trata 401 → login e **403 → `404.html?code=403`**: com sessão expirada o usuário cai na página de erro em vez do login. Também faltam os testes da tarefa (POST autenticado sem CSRF, sessão de conta bloqueada, mesmo e-mail logando nos dois perfis) e o token CSRF não é rotacionado no login (`rotate_token`). |
| **BE-026** `POST /auth/register/` | [x] | ✅ (com ressalvas) | Cliente e oficina (+ `PAG_WORKSHOP` na mesma transação), CSRF exigido, sessão aberta, `setup_complete=false`; 5 testes. Ressalvas: CNPJ duplicado devolve `409 {"detail":"Já existe uma conta com esses dados."}` sem o campo `cnpj` (o frontend mapeia erro por campo); faltam os testes de e-mail duplicado no mesmo perfil, senha fraca e rollback da transação; usa `@transaction.atomic` em vez de `@transactional`. |
| **BE-027** `POST /auth/login/` | [x] | ✅ | Mensagem única para e-mail inexistente/senha errada com hash fictício (tempo comparável), 403 só após senha correta, log de autenticação; 4 testes. A mensagem diz "Conta bloqueada" também para conta `inactive`. Sem teste de não enumeração por tempo. |
| **BE-028** `setup_complete` | [ ] | 🟡 **Parcial** | `workshops/domain.py:is_setup_complete` (≥1 serviço — DP-06 recomendada) e exposto em `/auth/me/`, login e cadastro (confirmado: `false` → `true` após cadastrar serviço). `IsWorkshopSetupComplete` existe em `core/permissions.py` mas **não é aplicada em nenhuma rota** e não há testes da regra. `/workshop/me/` é da Fase 3 (BE-037). |
| **BE-029** `/auth/me/` e logout | [x] | ✅ | `ensure_csrf_cookie` também no 401 (testado), logout com `session.flush()` → 204 e sessão inválida depois (testado). |
| **BE-030** Permissões anti-BOLA | [ ] | 🟡 **Parcial** | `IsClient`, `IsWorkshop`, `IsAdmin`, `IsChatParticipant`, `IsWorkshopSetupComplete` (`core/permissions.py`) e `OwnedByClientMixin`/`OwnedByWorkshopMixin` (`core/mixins.py`) existem, **sem nenhum teste** e sem uso real ainda. Critério "visitante → 401" falha (ver BE-025). |
| **BE-031** `PATCH /me/` e `POST /me/password/` | [ ] | 🟡 **Parcial, com defeitos** | Rotas existem. **Defeitos confirmados:** (1) upload de foto em multipart responde `400 {"photo_profile":["Não é uma string válida."]}` — o campo é `CharField` (`accounts/serializers.py:57`), então a validação falha antes do `validate()`; (2) se a imagem fosse inválida, `process_image` levantaria `InvalidImageError` não tratado → **500** (`accounts/services.py:184` e `:209`); (3) o arquivo antigo é apagado **antes** do commit (deveria usar `apply_image_changes`); (4) a troca de senha **não invalida as outras sessões** (confirmado: a segunda sessão continua 200) — o próprio código admite em `accounts/views.py:193`; (5) `/me/password/` devolve 200 com `detail` (contrato: 204). Sem testes. |
| **BE-032** Redefinição de senha | [x] | ⚠️ **Funciona, sem testes** | Confirmado por sondagem: resposta idêntica para e-mail existente/inexistente, e-mail enviado, token assinado de 1 h com *fingerprint* do hash, reutilização → 400. **Não há nenhum teste automatizado** (a tarefa exige testes de API e do outbox). Exceções são engolidas sem log (`accounts/views.py:217-232`); o envio síncrono do e-mail cria diferença de tempo entre e-mail existente e inexistente; responde 200 (contrato: 204 — o frontend aceita ambos). |
| **BE-033** Rate limiting | [ ] | 🟡 **Parcial** | Throttles `login`/`register`/`reset` aplicados nas views (confirmado: 6º login inválido → 429). Faltam: `MessageRateThrottle` (será usado no chat), atraso progressivo/bloqueio temporário, testes, e cache compartilhado — o cache é `LocMemCache` (`settings/base.py:227`), que **não** é compartilhado entre processos do Gunicorn. |
| **BE-034** CORS, CSRF e cookies | [x] | ✅ | Origens explícitas em dev (5500), `CORS_ALLOW_CREDENTIALS`, `x-csrftoken` liberado, cookies `Secure` por padrão fora do DEBUG, `CORS_ALLOW_ALL_ORIGINS` proibido em prod (testado). Falta o teste com cabeçalho `Origin` exigido pela tarefa. |
| **BE-035** (Cond.) Admin/moderação | [ ] | 🟡 **Parcial** | DP-03 aceita (admin = usuário Django `is_staff`). A autenticação já reconhece `is_staff` e `IsAdmin` existe, mas não há `apps/moderation/permissions.py`, rotas `/api/admin/*`, log de auditoria nem testes. |

### 5.2 Resultado da sondagem (teste descartável, fora do repositório)

| Chamada | Resposta obtida | Esperado (backlog/contrato) |
|---|---|---|
| Visitante `GET /api/workshop/services/` | 403 | **401** |
| Visitante `PATCH /api/me/` · `POST /api/auth/logout/` | 403 · 403 | **401** |
| Cliente `PATCH /api/me/` multipart com JPEG válido | 400 "Não é uma string válida." | **200** com foto salva |
| Cliente `PATCH /api/me/` com `email` no corpo | 200, e-mail inalterado | ✅ |
| `POST /api/me/password/` e reuso de outra sessão | 200; outra sessão continua válida | **204**; outra sessão inválida |
| Redefinição: e-mail existente × inexistente | 200 idênticos; 1 e-mail no outbox | ✅ |
| Confirmar token / reutilizar token | 200 / 400 | ✅ (contrato: 204 no sucesso) |
| 7 logins inválidos seguidos | 401 ×5, 429 ×2 | ✅ |
| `setup_complete` antes/depois de 1 serviço | `false` / `true` | ✅ |
| Cadastro com CNPJ já usado | 409 `{"detail": …}` | 409/400 **com campo `cnpj`** |
| `GET /api/catalog/services/` | 200 | rota não prevista (inclusão duplicada) |
| `GET /api/services/` (item) | `{id,name,description,id_category}` | contrato: `{id,name,description,id_service_category,category_name}` |

---

## 6. Pendências encontradas (o que falta para fechar as Fases 0–2)

Ordenadas por prioridade. "Bloq." = deve ser resolvida antes da Fase 3.

| ID | Tarefa | Bloq. | Pendência | Onde |
|---|---|:-:|---|---|
| P-01 | BE-025/030 | ✅ | Responder **401** para visitante em endpoint protegido: implementar `authenticate_header` em `AccountSessionAuthentication` (ex.: `return 'Session'`) e testar 401 × 403 × 404. | `apps/accounts/authentication.py` |
| P-02 | BE-031 | ✅ | Corrigir `PATCH /me/`: usar `ImageURLField` (BE-021) para `photo_profile`, tratar imagem inválida como 400, trocar a remoção imediata por `apply_image_changes` (apaga após o commit). | `apps/accounts/serializers.py`, `services.py` |
| P-03 | BE-031 | ✅ | Trocar a senha deve invalidar as **outras** sessões (ex.: guardar na sessão o *fingerprint* do `password_hash` e recusá-la em `AccountSessionAuthentication` quando divergir — vale também após a redefinição de senha). Responder 204. | `authentication.py`, `views.py` |
| P-04 | Lint/CI | ✅ | Zerar os 25 erros do `ruff check .` (o CI está vermelho). | vários (seção 1) |
| P-05 | — | ✅ | **Commitar** a Fase 2 (34 caminhos pendentes no `git status`). | — |
| P-06 | BE-028/030 | ✅ | Testes de `is_setup_complete`, das permissões (`IsClient`, `IsWorkshop`, `IsAdmin`, `IsChatParticipant`, `IsWorkshopSetupComplete`) e dos mixins de dono; definir onde `IsWorkshopSetupComplete` será aplicada (todas as rotas `/workshop/*` exceto as do assistente: `me`, `page`, `operation-hours`, `point`, `services`, `points-of-interest`). Marcar BE-028 concluída quando a permissão estiver aplicada e testada (o teste de `GET /workshop/attendances/` → 403 entra com BE-049). | `apps/core/`, `apps/workshops/` |
| P-07 | BE-032 | | Testes de redefinição (resposta idêntica, outbox, token reutilizado, token expirado com relógio controlado); registrar em log as exceções hoje engolidas. | `apps/accounts/tests/` |
| P-08 | BE-025 | | Testes: POST autenticado sem CSRF → 403; sessão de conta bloqueada recusada; mesmo e-mail logando como cliente e como oficina; `rotate_token` no login. | `apps/accounts/` |
| P-09 | BE-026 | | Devolver `{"cnpj":[…]}` / `{"email":[…]}` no conflito de cadastro (usar `translate_db_error`/constraint em vez do 409 genérico); testes de duplicidade, senha fraca e rollback. | `apps/accounts/services.py` |
| P-10 | BE-033 | | Cache compartilhado para throttling em produção (Redis ou `DatabaseCache`), atraso/bloqueio progressivo após falhas repetidas, testes de 429 e de não regressão do polling. | `settings`, `core/throttles.py` |
| P-11 | BE-035 | | Concluir: `IsAdmin` aplicada em `/api/admin/*` (rotas reais na Fase 5), log de auditoria das ações de admin, testes (cliente → 403, `is_staff` → 200). | `apps/moderation/` |
| P-12 | BE-001 | | Criar `backend/docs/adr/` com um ADR por decisão (DP-01…DP-23), Status **"Aceito por padrão (recomendação do backlog)"** e data, mais o índice `README.md`. | `backend/docs/adr/` |
| P-13 | BE-016 | | Testes de `SamPagination` (forma `{count,next,previous,results}`, `next` relativo com `?page=`), `SamModelSerializer` (sempre `id`) e `CommaSeparatedFilter`. | `apps/core/tests/` |
| P-14 | BE-002 | | Remover a inclusão duplicada do catálogo e alinhar os prefixos em `config/urls.py` ao contrato da seção 8 (`/chats/`, `/admin/`, `/favorites/`, `/budgets/`, `/workshops/{id}/`, `/map/points/`, `/points-of-interest/`, `/denunciations/`, `/reviews/`). Fazer junto com as rotas da Fase 3. | `backend/config/urls.py` |
| P-15 | BE-034 | | Teste de CORS com cabeçalho `Origin` (permitida × não listada). | `tests/` |
| P-16 | BE-003 | | Varredura de segredos no CI (gitleaks ou equivalente) e documentar `FRONTEND_BASE_URL`, `THROTTLE_*`, `CACHE_*` no `backend/.env.example`. | `.github/workflows/`, `.env.example` |
| P-17 | BE-005 | | Concluir `setup.sh` (criar também o `.env` da raiz) e adicionar healthcheck da `api` no compose. | raiz |
| P-18 | BE-007 | | Documentar a convenção de migrations futuras (RunSQL de ida e volta; recriar `vw_promotion_effective` quando alterar PROMOTION). | `backend/docs/` |
| P-19 | BE-027 | | Mensagem distinta para conta `inactive` × `blocked` (opcional). | `accounts/services.py` |
| P-20 | BE-006/011 | | Teste de concorrência do pool e `EXPLAIN` dos índices (podem ficar para BE-080/BE-083). | — |

---

## 7. Trabalho já iniciado da Fase 3 (fora do escopo, registrado para continuidade)

| Tarefa | Situação | Observações |
|---|---|---|
| BE-036 Catálogo global | 🟡 Parcial | `GET /api/service-categories/` e `GET /api/services/?q=&category=` públicos. O serializer de serviço devolve `id_category` em vez de `id_service_category` e não traz `category_name` (contrato §8.2). Sem testes. |
| BE-041 Serviços da oficina | 🟡 Parcial | `GET/POST /api/workshop/services/` (catálogo global ou personalizado `pending`). Faltam `PATCH /workshop/services/{id}/`, mapeamento das duplicidades para 409 com campo, testes. A view é `APIView` com verificação de perfil manual (deveria usar `IsWorkshop`). |

---

## 8. Itens de qualidade observados (não bloqueiam)

- `apps/core/tests/factories.py` agora gera o hash com `make_password` no import (Argon2) — funciona, mas deixa a importação mais lenta.
- `register_account` verifica o e-mail antes de inserir (corrida possível); o `IntegrityError` é capturado, mas com mensagem genérica (P-09).
- `PasswordResetConfirmView` e `ChangePasswordView` duplicam lógica de hash/sessão que caberia em `services.py` (camada de serviços do ADR de arquitetura).
- `frontend/js/config.js` já está com `DRIVER:'http'` e `API_BASE:'http://localhost:8000'`, enquanto `frontend/README.md` e `CLAUDE.md` ainda descrevem `local` como padrão e citam `tests/mock-api/server.py`, que não existe no repositório.
- As mudanças do frontend para CNPJ alfanumérico (`register.html`, `register.js`, `components-parts.js`) estão coerentes com o backend (`validators.py`) e não commitadas.
- O `README.md` da raiz estava vazio no HEAD e apagado na árvore de trabalho; o novo `README.md` traz o plano de continuidade.

---

## 9. Veredito

| Fase | Pode ser considerada concluída? | Condição |
|---|---|---|
| 0 | **Sim**, com P-12 (ADRs em arquivo) a registrar. | Decisões = recomendações do backlog. |
| 1 | **Sim.** | P-13 (testes da base da API) recomendado antes da Fase 3. |
| 2 | **Não.** | Resolver P-01 a P-06 (bloqueadoras) e, de preferência, P-07 a P-11; então marcar BE-028, BE-030, BE-031, BE-033 e BE-035 (esta condicionada às rotas da Fase 5) e reavaliar BE-025/BE-032. |
