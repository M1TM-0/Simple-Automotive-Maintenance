# SAM — Validação final e aceite (BE-094)

> **Situação em 18/11/2026: aceite NÃO concedido — aguardando a revisão e a assinatura do
> responsável (seção 7).** As decisões do BE-094 foram implementadas e validadas no
> staging local (`https://sam.localhost`), com as evidências abaixo. Os itens que ainda
> dependem de outra pessoa, de tempo de observação ou de serviço externo estão listados
> como tal (seção 1). Item P0 com falha impede o aceite.

Legenda: ✅ implementado e validado (evidência) · 🟡 implementado, validação parcial ou
ainda não observada · ⏳ pendente (outra pessoa / tempo) · ⛔ bloqueado por dependência
externa · ⚠️ adiado formalmente.

Documentos de apoio: `backend/docs/STAGING.md` (procedimento e evidências do staging),
`backend/docs/RELATORIO-BE-094.md` (relatório final), ADRs 0024–0026, `RUNBOOK.md`.

## 1. Resumo do BE-094

### Implementado e validado ✅

| Requisito | Evidência |
|---|---|
| Tiles `tile.openstreetmap.org` com atribuição "© OpenStreetMap contributors" | Staging, Chromium 159 e Firefox 159: 21 e 22 tiles, **todos 200**, Referer `https://sam.localhost/`; atribuição no controle do Leaflet (link `/copyright`), na legenda e em cada popup (`tests/e2e/test_staging.py`) |
| Política de uso dos tiles (Referer, cache, sem download em massa) | `referrerPolicy: 'strict-origin-when-cross-origin'` na camada (a página usa `same-origin`); nenhum proxy/pré-carga; `staging.sh check`: tile com Referer da origem → 200 `image/png` |
| Oficinas do SAM no mapa (fonte própria, funções preservadas) | `/api/map/points/` inalterado; suíte E2E F1–F8 nos dois navegadores; staging: 3 oficinas listadas e com pino |
| Estabelecimentos do OSM pela Overpass (`amenity=fuel`, `shop=car_repair`, `shop=tyres`, `shop=repair`, `shop=car_parts`, `amenity=car_wash`), região visível | `GET /api/map/external-points/` (ADR 0024); staging com dados **reais** do OSM (instância pública `maps.mail.ru`): 28 estabelecimentos + 3 oficinas do SAM, nos dois navegadores |
| Cache, tempo limite, indisponibilidade e limites da Overpass | 49 testes com uma Overpass simulada por servidor HTTP real (`apps/workshops/tests/test_overpass.py`): 429/502/503/504/400, tempo esgotado, JSON inválido, resposta incompleta ou grande demais, recuo exponencial, orçamento por minuto, cache por célula, `too_large`, `disabled` |
| Overpass fora do ar não afeta o SAM | Staging com falha injetada (`overpass.invalid`): `unavailable` em ~8 ms, aviso, oficina do SAM no mapa e na lista — 6/6 testes em cada navegador; a instância padrão `overpass-api.de` ficou sem capacidade a validação inteira e o SAM degradou como esperado; E2E simulado (`tests/e2e/test_map_openstreetmap.py`) |
| Diferenciação visual; nada exclusivo das oficinas para os externos | Losango âmbar (forma e tamanho distintos) × pino em gota; popup "não cadastrado no SAM" com link para o OSM, sem perfil/chat/favorito/solicitação; fora da lista lateral (E2E e captura de tela do staging) |
| Sem duplicações evidentes | Mesmo id do OSM, ≤ 5 m, ou nome parecido a ≤ 100 m (testes de unidade, API e E2E) |
| Licença ODbL e atribuição | Atribuição no mapa, legenda, popups e na resposta da API; dados do OSM só em cache, nada gravado nas tabelas (ADR 0024) |
| Backup PostgreSQL diário, procedimento reproduzível, armazenamento separado | Serviço `backup` (agendador corrigido, ADR 0025); `staging.sh backup`; volume `sam-staging_backups` ≠ `sam-staging_pgdata` ≠ volumes de dev; 9 backups cifrados gerados no staging |
| Restauração real em banco isolado, integridade, tempo medido | `staging.sh restore-drill`: PostgreSQL 16 descartável (rede interna, tmpfs); sha256, `pg_restore` em transação única, contagens **e md5 do conteúdo das 36 tabelas**, 1 imagem por hash, `check_schema`, `migrate --check`, `/ready/` 200 — **5,6 s** no total |
| RTO 8 h | Medido: 5,6 s (restauração + API) e ≈ 1 min para construir e subir a pilha do zero nesta máquina — para o volume atual (ver limitação em 🟡) |
| Staging local isolado, Docker Compose, PostgreSQL próprio, HTTPS confiável, `https://sam.localhost`, sem exposição | `deploy/staging/` (ADR 0026); `staging.sh check` 13/13 (TLS 1.3 válido sem `-k`, portas só em 127.0.0.1/[::1]); `deploy/smoke-test.sh` 42/42 |
| Certificado validado nos navegadores do E2E | Chromium e Firefox com a CA num banco de certificados próprio, **sem** `ignore_https_errors`; controle negativo: sem a CA, `ERR_CERT_AUTHORITY_INVALID` / `SEC_ERROR_UNKNOWN_ISSUER` |
| E2E completo em Chromium e Firefox | `pytest -m e2e`: 29 testes (14 por navegador + 1 independente) — ver seção 5; `pytest -m staging`: 6 × 2 navegadores |

### Implementado, validação parcial ou ainda não observada 🟡

| Item | O que falta |
|---|---|
| RPO 24 h | Agendador diário com recuperação de atraso (testado, inclusive a regressão da deriva para 26 h) e primeiro backup automático observado; **a execução diária ao longo de vários dias não foi observada** (staging criado em 18/11/2026). Próxima execução automática: 19/11/2026 03h (America/Sao_Paulo). Conferir `job_heartbeat` / `staging.sh compose logs backup` depois disso |
| RTO com volume realista | O ensaio usou a base de demonstração (357 linhas). Repetir `restore-drill` com dados realistas antes de afirmar o RTO para outro volume |
| Provedor de tiles trocável | `SAM.config.MAP_TILES` + CSP documentados; a troca por outro provedor não foi exercitada |
| Instância padrão da Overpass | O caminho "disponível" foi validado com a instância pública `maps.mail.ru`; a `overpass-api.de` (padrão do código) esteve sem capacidade durante toda a validação. O staging ficou configurado com `maps.mail.ru` e tempo limite de 30 s |

### Pendente ⏳

| Item | Responsável |
|---|---|
| Revisão e assinatura do aceite (seção 7) | Responsável pelo projeto |
| Runbook executado por outra pessoa num ambiente limpo | Revisor do runbook |
| Roteiro manual das 26 telas por uma pessoa (a cobertura automatizada percorre todas: F1–F8 + mesma origem/CSP com 27 telas/estados, nos dois navegadores) | Responsável |
| Carga de polling (`tests/perf/polling_load.py`) com o Nginx na frente | Exige semear 2.000 contas no banco-alvo; não executado no staging de demonstração |

### Bloqueado por dependência externa ⛔

| Item | Situação |
|---|---|
| Overpass pública `overpass-api.de` | Respondeu "502 — at capacity" ou estourou o tempo em todas as tentativas de 18/11/2026 (também `overpass.private.coffee` e `overpass.kumi.systems`). Não impede o SAM (ver ✅) e há alternativa por configuração (`SAM_OVERPASS_URL`) |

### Adiado formalmente ⚠️

| Item | Motivo |
|---|---|
| E2E em WebKit | Fora do escopo por decisão do responsável (BE-094) |
| Telas T27/T28 (moderação no frontend) | Django Admin é a interface provisória (ADR 0003) |
| Aviso preventivo à oficina e intervalo por tempo | ADR 0005 |
| Uma réplica da API (segundos de 502 na troca de versão) | Aceito para o volume atual (ADR 0022) |

## 2. Critérios de conclusão (seção 16 do `backlog/backlog_backend.md`)

### Banco e API

| Item | Situação | Evidência |
|---|---|---|
| `migrate` em banco vazio → 23 tabelas, 3 views, 16 triggers, 26 funções, 62 serviços, idênticos ao `init.sql` | ✅ | `apps/core/tests/test_schema_and_models.py`; `manage.py check_schema` (rodado pelo `deploy.sh` a cada implantação do staging e no `smoke-test.sh`) |
| Os 84 endpoints da seção 8 existem, estão no OpenAPI e respondem conforme o contrato | ✅ | `tests/contract/test_contract.py`: 91 operações (84 + 3 de saúde + 3 das Fases 3–5 + 1 do BE-094) com 2xx validado em modo estrito; matriz de autorização com as mesmas 91 |
| `/api/health/ready/` 200 e schema OpenAPI válido | ✅ | `spectacular --validate --fail-on-warn` sem avisos; staging: `/api/health/`, `/ready/` e `/jobs/` = 200 pelo HTTPS |

### Integração com o frontend

| Item | Situação | Evidência |
|---|---|---|
| Com `DRIVER:'http'`, nenhuma tela mostra "servidor indisponível" nem guarda dado de domínio no `localStorage` | ✅ | `tests/e2e/test_same_origin_csp.py` (27 telas/estados, mesma origem, CSP de produção) **em Chromium e Firefox**; staging: telas do cliente e da oficina pelo HTTPS |
| F1–F8 passam em Chromium, Firefox e WebKit | ✅ / ⚠️ | F1–F8 + 2 cenários de falha passam em **Chromium e Firefox** (seção 5); **WebKit adiado** por decisão |
| Nenhum dado fictício; credencial demonstrativa ausente (FE-11) | ✅ | FE-11; os dados do staging são criados pela API e marcados "[Demonstração]" |

### Regras de negócio

| Item | Situação | Evidência |
|---|---|---|
| 14 transições do atendimento (e as proibidas); 16 triggers com teste positivo e negativo | ✅ | `tests/db_rules/` |
| Histórico gerado só na entrega e idempotente | ✅ | `tests/db_rules/test_records.py` |
| Vencidos expirados em até 5 min pelo job, com alerta de heartbeat | ✅ | Rotina a cada 60 s no staging (batimento `expiration`); alerta do monitor — ver seção 4 |
| Notificações geradas pelos eventos previstos | ✅ | `apps/notifications/tests/` |

### Segurança

| Item | Situação | Evidência |
|---|---|---|
| 401/403/404 em todos os endpoints; mass assignment ignorado | ✅ | `tests/security/test_authz_matrix.py` (inclui `/map/external-points/`, pública) |
| Nenhuma senha/token/cookie em log; sem segredos no repositório; `pip-audit` sem vulnerabilidade | ✅ | `pip-audit`: nenhuma vulnerabilidade conhecida (18/11/2026, com Playwright 1.65.2); segredos do staging fora do repositório (`~/.local/share/sam-staging`, 0700) |
| Uploads validados e reprocessados; `check --deploy` sem avisos | ✅ | `check --deploy --fail-level WARNING` limpo; upload pelo HTTPS do staging e no `smoke-test.sh` |
| IP do cliente atrás do proxy | ✅ | `tests/security/test_client_ip.py` |
| Chamada a serviço externo segura (BE-094) | ✅ | Esquema da URL conferido, tempo limite, resposta ≤ 5 MB, cache, orçamento, recuo; limite por IP no endpoint |

### Qualidade e operação

| Item | Situação | Evidência |
|---|---|---|
| Cobertura e lint na meta; concorrência e desempenho nos limites | ✅ / ⏳ | Cobertura 97,22 % (meta 90 %), ≥ 95 % em serviços/permissões/seletores; `ruff check` limpo; `ruff format --check` limpo e bloqueante no CI (P-23, commit de formatação `483a446`); sem N+1 (inclui a rota nova); carga de polling com o Nginx ⏳ |
| Backup executado e restauração testada | ✅ | Seção 1 e `STAGING.md` §5.4; `-m deploy`: 51/51 (inclui o ensaio automatizado com md5) |
| Runbook validado por outra pessoa | ⏳ | — |
| Decisões DP resolvidas ou aceitas em ADR | ✅ | 26 ADRs; tiles (0024), fonte dos pontos de interesse (0024), RPO/RTO (0025), staging e navegadores (0026) decididos pelo responsável |

## 3. Implantação (seção 13.7 — checklist de go-live)

| Item | Situação | Evidência |
|---|---|---|
| `check --deploy` sem avisos e `DEBUG=False` | ✅ | Staging com `config.settings.prod` |
| HTTPS ativo e redirecionamento de HTTP | ✅ (staging local) | TLS 1.3 com certificado da CA local, HTTP → HTTPS 301; certificado público (Let's Encrypt) não se aplica ao staging local |
| Backup executado e restauração testada | ✅ | Seção 1 |
| Job de expiração agendado e com alerta de heartbeat | ✅ | Serviço `jobs` + monitor (seção 4) |
| Credencial demonstrativa ausente do login | ✅ | FE-11 |
| Provedor de tiles definido (FE-10) | ✅ | OSM público (ADR 0024) |
| Decisões DP aceitas em ADR | ✅ | `backend/docs/adr/README.md` |

## 4. Roteiro em staging (executado em 18/11/2026)

| Passo | Resultado |
|---|---|
| 1. Subir o staging pelo `deploy.sh` (`staging.sh init` + `up`) | ✅ 6 implantações (`be094-1`…`be094-6`, a última com o código final); a primeira expôs um defeito do `deploy.sh` (corrigido) |
| 2. `deploy/smoke-test.sh` | ✅ 42/42 (só no loopback) — primeira execução real; antes das correções desta sessão o upload e a restauração teriam falhado |
| 3. Backup e restauração num banco novo e isolado | ✅ 5,6 s; ver seção 1 |
| 4. E2E apontado para o staging | ✅ `pytest -m staging`, Chromium e Firefox (Overpass disponível e indisponível) |
| 5. Alertas: banco fora do ar (≤ 2 min) e `jobs` parado | ✅ banco: 76 s (`smoke-test.sh`); `jobs`: alerta com 15 min e resolução automática (seção 6) |
| 6. Decisões do responsável | ✅ ADRs 0024–0026 |

## 5. Resultados dos testes (18/11/2026)

| Suíte | Resultado |
|---|---|
| `pytest` (padrão, PostgreSQL 16 descartável) | **1992 passaram**, 9 pulados (ensaio de backup: `pg_dump` 18 × servidor 16), cobertura 97,22 % |
| `pytest -m deploy` (PostgreSQL 18 descartável, ferramentas da mesma versão) | **51/51** |
| `pytest -m e2e` — Chromium 159 | 14/14 (F1–F8, 2 cenários de falha, mesma origem/CSP, 3 do mapa com OSM) |
| `pytest -m e2e` — Firefox 159 | 14/14 |
| `pytest -m e2e` — sem navegador | 1/1 |
| Instabilidade observada | F3 no Chromium falhou 1 vez em 5 rodadas completas (tela do mapa sem conteúdo; provável CDN do Leaflet); não reproduzido em 3 repetições nem na rodada final, 29/29 |
| `pytest -m staging` — Overpass disponível | Chromium 5 + Firefox 5 passaram; 2 pulados (ensaio de falha) |
| `pytest -m staging` — Overpass indisponível | Chromium 6/6, Firefox 6/6 |
| `deploy/smoke-test.sh` | 42/42 |
| `staging.sh check` | 13/13 |
| `ruff check`, `makemigrations --check`, `check`, `check --deploy`, `spectacular --validate --fail-on-warn`, `pip-audit` | Todos sem erro |
| Atualização P-21/P-23 (18/11/2026): `pytest` padrão no PostgreSQL 16 / 18 | 1995 passaram + 9 pulados / **2004 passaram** (o 18 aplica o `init.sql` original); E2E 29/29; `ruff format --check` limpo |

Falhas encontradas e corrigidas nesta validação: ver `RELATORIO-BE-094.md`, seção 7.

## 6. Registro de execuções

| Data | Ambiente | O que | Resultado |
|---|---|---|---|
| 2026-11-18 | Máquina de desenvolvimento | Suíte, cobertura, `check --deploy`, schema, `pip-audit`, E2E Chromium, ensaio de backup | Ver `README.md`, seção 7 (Fase 7) |
| 2026-11-18 | Staging local `https://sam.localhost` (CachyOS, Docker 29.9.3) | BE-094: staging, HTTPS, mapa/OSM, backup + restauração isolada, smoke test, E2E Chromium + Firefox | Seções 1, 4 e 5; `STAGING.md` |
| 2026-11-18 | Staging local | Alerta de rotina parada (`jobs` parado às 11:29:08 UTC) | ALERTA às 11:43:55 (15 min), RESOLVIDO às 11:44:25 após religar — `STAGING.md` §5.6 |
| 2026-11-18 | Máquina de desenvolvimento (PostgreSQL 16 do compose) | P-23: `ruff format .` global (commit exclusivo `483a446`, 135 arquivos, AST idêntico) + CI com `ruff format --check .` bloqueante | `pytest` 1992 passaram, 9 pulados (mesmo resultado de antes); `ruff check`/`ruff format --check` limpos |
| 2026-11-18 | PostgreSQL 16.15 (compose, bancos temporários) e 18.6 (cluster descartável) | P-21: `init.sql` com `public.clean_service_name`; banco vazio por `psql -f init.sql` e `manage.py migrate` | 23 tabelas, 3 views, 16 triggers, 26 funções, 62 serviços e `check_schema` OK nas duas versões; índices reconstruídos com `search_path` restrito e vazio; dump/restore no 18; suíte 1995 (16) / 2004 (18) passaram; E2E 29/29 |

## 7. Aceite

Revisão e assinatura **pendentes**. O preenchimento abaixo é do responsável.

| Papel | Nome | Data | Decisão |
|---|---|---|---|
| Responsável pelo projeto | | | ☐ Aceito ☐ Aceito com pendências ☐ Recusado |
| Revisor do runbook | | | |
