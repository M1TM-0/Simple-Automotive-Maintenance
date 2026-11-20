# Relatório final — BE-094 (validação em staging e aceite)

Data: 18/11/2026 · Ambiente: CachyOS (kernel 7.3), Docker 29.9.3 / Compose 5.7.0,
PostgreSQL 16 (staging e testes), Python 3.12, Playwright 1.65.2 (Chromium 159, Firefox 159).
Documento de aceite (assinatura pendente): `backend/docs/ACEITE.md`. Procedimento do
staging: `backend/docs/STAGING.md`. Decisões: ADRs 0024, 0025 e 0026.

## 1. Auditoria do estado inicial

| Requisito | Encontrado | Classificação |
|---|---|---|
| Tiles OSM + atribuição | `map.js` com `tile.openstreetmap.org` e atribuição, URL fixa no código; Nginx com `Referrer-Policy: same-origin` → tiles sairiam **sem Referer** (a política do OSM exige) | Parcial |
| Oficinas do SAM no mapa | `GET /api/map/points/` (UNION oficinas públicas + POIs importados, caixa + Haversine) | Pronto |
| Overpass / OSM em tempo real | Inexistente (só `import_pois` por arquivo; ADR 0010 com fonte "pendente") | Ausente |
| Backup / restauração | `deploy/backup/*` completo (GPG, manifesto com contagens, agendador, alerta) e ensaio automatizado, **nunca executados com Docker**; ADR 0022 com RTO-alvo 2 h | Implementado, não validado |
| Staging | Inexistente; `compose.prod.yml` com projeto padrão `sam`, que nesta máquina colidiria com o volume `sam_pgdata` do desenvolvimento | Ausente |
| E2E | Playwright 1.41 só com Chromium; Firefox não instalado nem configurado | Parcial |
| Ambiente | Docker acessível só via `newgrp docker` (grupo ainda não herdado pela sessão); sem `mkcert` nem sudo; `deploy/smoke-test.sh` nunca executado | — |

## 2. Alterações realizadas

**Backend**
- `apps/workshops/overpass.py` (novo): cliente da Overpass (stdlib, sem dependência nova),
  células de 0,05° com cache, orçamento por minuto, recuo exponencial, tempo limite,
  limite de bytes, normalização dos elementos, deduplicação com o SAM.
- `GET /api/map/external-points/` (view, serializers, rota, throttle `external_map`);
  `sam_points_for_dedup()` no seletor; settings `SAM_OVERPASS_*`; URL desligada nos testes.
- Migration `catalog/0002_normalize_service_name_schema` (restauração; ver seção 9).
- Testes: `test_overpass.py` (49), `test_restore_search_path.py` (2); contrato (91
  operações), matriz de autorização e detector de N+1 com a rota nova.

**Frontend**
- `js/map.js`: tiles por `SAM.config.MAP_TILES` (padrão OSM), `referrerPolicy`
  `strict-origin-when-cross-origin`, atribuição do OSM garantida, camada do OpenStreetMap
  (zoom ≥ 13, losangos, popup, filtros, liga/desliga, aviso de carregamento/falha),
  legenda. `js/api.js`: `map.external`. `css/map.css`: estilos. Comentários de
  `MAP_TILES` em `js/config.js` e `deploy/nginx/config.prod.js`.

**Backup**
- `sam-backup`/`sam-restore`/`lib.sh`: md5 do conteúdo de cada tabela no manifesto (mesmo
  snapshot do dump) e conferência na restauração.
- `sam-backup-loop`: agendamento diário com recuperação de atraso (corrige deriva para 26 h).

**Implantação e staging**
- `deploy/staging/` (novo): `staging.sh` (init, up, status, seed, check, backup,
  restore-drill, overpass, trust, compose, stop), `compose.staging.yml` (só loopback),
  `seed_demo.py` (dados de demonstração pela API).
- `deploy.sh`/`compose.sh`/`smoke-test.sh`: `SAM_COMPOSE_OVERRIDE`; `deploy.sh` corrigido
  (`SAM_VERSION` no `db_psql`).
- `backend/Dockerfile` e `compose.prod.yml`: dono do ponto de montagem da mídia no proxy e
  `nocopy` nos consumidores só-leitura (upload).
- `deploy/.env.prod.example` e `backend/.env.example`: variáveis da Overpass.

**E2E**
- `tests/e2e/conftest.py`: navegador parametrizado (Chromium e Firefox, `SAM_E2E_BROWSERS`).
- `tests/e2e/test_same_origin_csp.py`: mensagens de CSP e cancelamento do Firefox.
- `tests/e2e/test_map_openstreetmap.py` (novo): mapa com a Overpass simulada.
- `tests/e2e/test_staging.py` (novo, `-m staging`): staging no ar, HTTPS validado.
- Playwright 1.41.0 → 1.65.2 (`requirements/dev.txt`); CI instala `chromium firefox`.

**Documentação**: ADRs 0024–0026 (0010 e 0022 marcados como revistos), `STAGING.md`,
`ACEITE.md`, este relatório, `RUNBOOK.md` (§4, §7, §11), `migrations.md`,
`seguranca/checklist-endpoints.md`, `README.md`, `backlog_backend.md` (BE-094, sem marcar
concluída), `frontend/CLAUDE.md`, `frontend/README.md`, `frontend/PENDENCIAS-API.md`.

## 3. Mapa e tiles

- Provedor: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, `maxZoom` 19, sem `{s}`.
- Atribuição "© OpenStreetMap contributors" com link para `/copyright`: controle do
  Leaflet, legenda (com "licença ODbL") e popups dos estabelecimentos externos.
- Política de uso: Referer de origem nos tiles (`referrerPolicy`), cache HTTP do navegador
  intacto, sem proxy de tiles, sem pré-carga nem download em massa.
- Trocar o provedor: `SAM.config.MAP_TILES = { url, attribution, maxZoom }` + host em
  `img-src` de `deploy/nginx/snippets/csp-frontend.conf` (não exercitado).
- Evidência: staging, todos os tiles com status 200 e Referer `https://sam.localhost/`
  (21 no Chromium, 22 no Firefox); `staging.sh check`: tile com Referer → `200 image/png`.

## 4. Pontos de interesse

| | SAM | OpenStreetMap |
|---|---|---|
| Endpoint | `GET /api/map/points/` (inalterado) | `GET /api/map/external-points/?south&west&north&east` |
| Conteúdo | Oficinas cadastradas e pontos importados | `amenity=fuel`, `shop=car_repair`, `shop=tyres`, `shop=repair`, `shop=car_parts`, `amenity=car_wash` |
| No mapa | Pino em gota vermelho (oliva para ponto do SAM), lista lateral | Losango âmbar menor, só no mapa |
| Funções | Perfil, chat, favorito, atendimento, avaliação | Só exibição + link para o OSM |
| Falha | — | 200 com `status: unavailable` e aviso; o SAM não muda |

Proteções da Overpass: região visível com zoom ≥ 13; até 16 células de 0,05° (senão
`too_large`); cache por célula de 24 h; uma consulta por movimento (só as células que
faltam); 10 consultas/min no total; recuo de 60 s a 15 min depois de falha/429/5xx;
tempo limite 12 s; resposta ≤ 5 MB; 60 req/min por IP no endpoint. Duplicatas: mesmo id
do OSM num ponto importado, ≤ 5 m, ou nome parecido a ≤ 100 m. ODbL: atribuição em todos
os pontos de exibição; dados só em cache.

## 5. Backup e restauração

- Diário às 03h (America/Sao_Paulo), com recuperação de atraso; antes de cada
  atualização; manual (`staging.sh backup`).
- Arquivo cifrado com `pg_dump -Fc`, mídia e manifesto (linhas **e md5 do conteúdo** por
  tabela no mesmo snapshot), no volume `backups` — separado do volume ativo do banco e
  de qualquer dado de desenvolvimento.
- Restauração (`sam-restore`) só em banco/mídia vazios, com sha256, transação única,
  contagens, md5 por tabela e hash de cada imagem.
- Ensaio isolado e cronometrado: `staging.sh restore-drill`.

## 6. Evidências de RPO e RTO

| | Meta | Evidência | Situação |
|---|---|---|---|
| RTO | 8 h | `restore-drill` (be094-5): banco isolado 1,4 s + restauração e conferência 0,9 s + API de produção pronta 3,3 s = **5,6 s**; reconstruir e subir a pilha do zero ≈ 1 min | ✅ para o volume atual (36 tabelas, 368 linhas, 1 imagem); repetir com volume realista |
| RPO | 24 h | Agendador com intervalo ≤ 24 h (testado, inclusive a regressão de 26 h); primeiro backup automático na subida (10:51 UTC); 9 backups no volume; monitor alerta com 26 h | 🟡 mecanismo validado; recorrência diária ainda não observada (próxima: 19/11 03h) |

Os scripts existirem não foi tomado como prova: a primeira restauração real **falhou**
(seção 9) e só depois da correção o ensaio passou.

## 7. Staging e HTTPS

- `https://sam.localhost`, projeto `sam-staging` (volumes `sam-staging_*`), proxy só em
  127.0.0.1 e ::1 (80/443); banco sem porta publicada; `config.settings.prod`
  (`DEBUG=False`); segredos em `~/.local/share/sam-staging` (0700).
- CA local (OpenSSL, `nameConstraints` = `sam.localhost`) — equivalente ao mkcert sem
  root; certificado de 397 dias; TLS 1.3.
- Verificações: `staging.sh check` 13/13; `smoke-test.sh` 42/42 (só no loopback); alerta
  do monitor com o `jobs` parado: disparou com 15 min e resolveu ao religar.
- Versão final no ar: `be094-6`.
- O banco de desenvolvimento (`sam-db`, `sam_pgdata`) não foi tocado; os testes usaram
  PostgreSQL descartáveis (16 em contêiner tmpfs e 18 local).

## 8. E2E em Chromium e Firefox

| Suíte | Chromium 159 | Firefox 159 | Sem navegador |
|---|---|---|---|
| `-m e2e`: F1–F8, 2 cenários de falha, mesma origem/CSP (27 telas/estados), 3 do mapa com OSM — rodada final | 14/14 | 14/14 | 1/1 |
| `-m e2e` — rodada anterior | 13/14 (F3 intermitente, seção 9) | 14/14 | 1/1 |
| `-m staging`, Overpass disponível | 5/5 (+1 pulado) | 5/5 (+1 pulado) | — |
| `-m staging`, Overpass indisponível | 6/6 | 6/6 | — |

O certificado é validado nos dois navegadores (CA num banco de certificados próprio, sem
`ignore_https_errors`), com controle negativo. Execuções intermediárias: 23/23 com
Playwright 1.41 e de novo com 1.65.2, antes dos testes novos do mapa.

## 9. Problemas encontrados e correções

| # | Problema | Como apareceu | Correção | Teste |
|---|---|---|---|---|
| 1 | `deploy.sh`: `db_psql` chamava o compose sem `SAM_VERSION`; a primeira implantação real parava em "Banco inacessível" | 1ª subida do staging | `compose_v` com a versão | `test_every_compose_call_has_a_version` (o `docker` falso agora exige a variável); mutação reprovada |
| 2 | Volume de mídia ficava `root` (o Docker copia o dono do ponto de montagem do **proxy** para o volume vazio) → todo upload dava 500 | Upload de foto no staging | `/var/www/media` com uid 10001 na imagem do proxy + `nocopy` nos consumidores só-leitura | `test_only_the_api_owns_the_media_volume`; upload no staging e no `smoke-test.sh` |
| 3 | **Nenhum backup era restaurável**: `normalize_service_name()` chama `clean_service_name()` sem schema e o `pg_restore` roda com `search_path` vazio | 1º `restore-drill` | Migration `catalog/0002` (chamada qualificada, resultado igual) | `test_restore_search_path.py` (reproduz o erro sem a migration); `restore-drill` e `smoke-test.sh` |
| 4 | Agendador do backup derivava para a cada 26 h quando a 1ª execução era depois das 07h (RPO real 26 h) | Revisão do estado do agendador no staging | Regra "sem sucesso desde a última ocorrência de `BACKUP_HOUR`" | `test_scheduler_keeps_the_daily_hour_and_catches_up`; mutação reprovada |
| 5 | Mapa dizia "Nenhum estabelecimento do OpenStreetMap" antes da resposta | E2E do mapa com Overpass simulada | Estado `loading` ("Buscando…") | `test_map_openstreetmap.py` |
| 6 | Firefox do Playwright 1.41 (NSS antigo) não reconhecia a CA local no perfil (`SEC_ERROR_UNKNOWN_ISSUER`); Firefox 160 do sistema e Firefox 159 do 1.65 reconhecem | `test_staging.py` no Firefox | Playwright 1.65.2 | `test_https_is_trusted_through_the_local_ca[firefox]` + controle negativo |
| 7 | Detector de N+1 chamava a rota nova sem a caixa (400) | Suíte completa | `QUERY` com parâmetros obrigatórios + Overpass simulada | `test_query_counts.py` |
| 8 | Mensagens de CSP e cancelamento de requisição do Firefox têm outro texto | Parametrização do E2E | Padrões para os dois navegadores | `test_same_origin_csp.py[firefox]` |

| 9 | F3 no Chromium falhou **1 vez** em 5 rodadas completas: a tela do mapa ficou sem conteúdo (scripts parados) | Penúltima rodada E2E | **Não corrigido**: não reproduzido em 3 repetições isoladas nem na rodada final (29/29); causa provável é o `<script>` síncrono do Leaflet servido por CDN externo (`unpkg.com`). Recomendação: servir o Leaflet a partir do próprio site (hoje é decisão do frontend: CDN com SRI) | — |

Os itens 1–4 eram defeitos latentes da Fase 7 que só a execução real com Docker revelou.

## 10. Pendências restantes

| Classificação | Item |
|---|---|
| ⏳ Pendente (pessoa) | Revisão e **assinatura** do aceite; runbook executado por outra pessoa; roteiro manual das 26 telas |
| ⏳ Pendente (tempo) | Observar o backup diário automático por alguns dias (`job_heartbeat`) |
| ⏳ Pendente (recomendação) | Leaflet servido pelo próprio site em vez do CDN `unpkg.com` (falha intermitente do item 9 da seção 9) |
| ⏳ Pendente | Carga de polling com o Nginx na frente (exige semear 2.000 contas no banco-alvo); ensaio de restauração com volume realista; troca de provedor de tiles não exercitada |
| ⏳ Decisão do responsável | P-21 (`init.sql` em PostgreSQL 17+; a restauração já não depende disso), P-23 (formatação) — *atualização 18/11/2026: P-23 fechada (commit de formatação `483a446`, CI bloqueante); P-21 corrigida no `init.sql` e validada no PostgreSQL 16 e 18 (README, seção 4.2)* |
| ⛔ Dependência externa | `overpass-api.de` sem capacidade durante toda a validação (502/tempo esgotado; idem `overpass.private.coffee` e `overpass.kumi.systems`); o staging usa a instância pública `maps.mail.ru` (lenta, também respondeu 504 uma vez) |
| ⚠️ Adiado | WebKit (decisão); T27/T28; aviso preventivo à oficina |
| — | Nada foi commitado nesta sessão |
