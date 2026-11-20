# SAM — Staging local (BE-094)

Staging **exclusivamente local**, nesta máquina (CachyOS), em `https://sam.localhost`:
a mesma implantação de produção (`deploy/compose.prod.yml` + `deploy/deploy.sh`), num
projeto Docker isolado, com HTTPS de uma CA local e o proxy publicado só no loopback.
Decisões: ADR 0026 (staging e navegadores), 0024 (mapa) e 0025 (backup).

## 1. O que é isolado do desenvolvimento

| | Desenvolvimento (`docker-compose.yaml`) | Staging local |
|---|---|---|
| Projeto Docker | `sam` | `sam-staging` |
| Banco | `sam-db`, volume `sam_pgdata`, porta 5432 publicada | `sam-staging-db-1`, volume `sam-staging_pgdata`, **sem porta publicada** |
| Mídia | `sam_media_data` | `sam-staging_media` |
| Backups | — | `sam-staging_backups` (separado do volume do banco) |
| API | `runserver` :8000 (DEBUG) | Gunicorn, `config.settings.prod`, só na rede interna |
| Frontend | `http.server` :5500 | Nginx com TLS, mesma origem, CSP de produção |
| Endereço | `http://localhost:5500` | `https://sam.localhost` (127.0.0.1/::1, portas 80/443) |
| Segredos | `.env`, `backend/.env` | `~/.local/share/sam-staging/` (0700, fora do repositório) |

Nada do staging lê ou grava os volumes de desenvolvimento.

## 2. Pré-requisitos

- Docker com Compose v2 e acesso ao daemon (usuário no grupo `docker`; numa sessão aberta
  antes de entrar no grupo, use `newgrp docker`).
- `openssl`, `curl`, `jq`, `python3`; `certutil` (pacote `nss`) para os testes E2E.
- Portas 80 e 443 livres no loopback.

## 3. Subir

```bash
deploy/staging/staging.sh init     # segredos aleatórios, CA local e certificado (uma vez)
deploy/staging/staging.sh up       # build + deploy.sh (migrate, check_schema, /ready, jobs)
deploy/staging/staging.sh seed     # dados de demonstração pela API (idempotente)
deploy/staging/staging.sh check    # verificação rápida (TLS, saúde, mapa, OSM, tiles)
```

- **Certificado**: CA local criada com OpenSSL (`nameConstraints` = `sam.localhost`: a CA
  não consegue assinar nenhum outro nome) e certificado de 397 dias para `sam.localhost`.
  É a mesma ideia do mkcert, sem instalar nada como root.
- **Confiar no navegador do dia a dia** (opcional): `deploy/staging/staging.sh trust`
  mostra como; `trust --install` importa a CA no Chromium/Chrome (`~/.pki/nssdb`) e nos
  perfis do Firefox. Os testes automáticos não dependem disso.
- **Dados de demonstração** (`seed`): 1 cliente e 4 oficinas "[Demonstração]" (3 na Av.
  Paulista, 1 em Teresina), com ponto, horários e serviço; senhas aleatórias em
  `~/.local/share/sam-staging/demo-accounts.json` (0600).
- Outros comandos: `status`, `backup`, `restore-drill`, `overpass URL|default`,
  `compose ps|logs -f api|…`, `stop` (para sem apagar volumes).

Remover tudo do staging (destrutivo, só se quiser recomeçar):
`deploy/staging/staging.sh compose down -v` — apaga **apenas** os volumes `sam-staging_*`.

## 4. Validar

```bash
cd backend
SAM_STAGING_URL=https://sam.localhost venv/bin/pytest -m staging            # Chromium + Firefox

# Ensaio de indisponibilidade da Overpass (falha real: host .invalid)
../deploy/staging/staging.sh overpass https://overpass.invalid/api/interpreter
SAM_STAGING_URL=https://sam.localhost SAM_STAGING_EXPECT_OVERPASS=down venv/bin/pytest -m staging
../deploy/staging/staging.sh overpass default

# Backup e restauração isolada, cronometrada
../deploy/staging/staging.sh backup
../deploy/staging/staging.sh restore-drill
```

`tests/e2e/test_staging.py` (6 testes × 2 navegadores) dá a cada navegador um banco de
certificados só com a CA do staging — o HTTPS é **validado**, sem `ignore_https_errors` —
e confere: TLS (emissor, protocolo, nome), recusa sem a CA (controle negativo), HTTP →
HTTPS, tiles do OSM (status 200, Referer = origem), atribuição, oficinas do SAM, camada do
OpenStreetMap (ou o aviso de indisponibilidade), fluxos de cliente e oficina. Evidências
por navegador em `backend/e2e-artifacts/staging-<navegador>.json`.

## 5. Evidências (18/11/2026)

Máquina: CachyOS (kernel 7.3), Docker 29.9.3, Compose 5.7.0. Versões implantadas
`be094-1` … `be094-6` (cada correção reimplantada pelo `deploy.sh`, com backup antes da
migração a partir da segunda); `be094-6` é o código final.

### 5.1 HTTPS e saúde — `staging.sh check` (be094-5 e be094-6): 13/13 ok

TLS válido pela CA local (curl sem `-k`), TLS 1.3, HTTP → HTTPS (301), portas 80/443 só em
127.0.0.1/[::1], `/api/health/`, `/ready/`, `/jobs/` = 200, CSP com os tiles do OSM,
`map.js` com atribuição e `referrerPolicy`, 4 oficinas no mapa, endpoint do OSM com 200,
tile do OSM com Referer da origem = 200 `image/png`.

### 5.2 Navegadores — `pytest -m staging`

| Execução | Chromium 159 (headless shell) | Firefox 159 |
|---|---|---|
| Overpass disponível (instância `maps.mail.ru`; a `overpass-api.de` estava sem capacidade), `SAM_STAGING_EXPECT_OVERPASS=up` | 5 passaram, 1 pulado (ensaio de falha) | 5 passaram, 1 pulado |
| Ensaio de falha (`SAM_STAGING_EXPECT_OVERPASS=down`) | 6/6 | 6/6 |

TLS nos dois: emissor "SAM staging local CA", TLS 1.3, `sam.localhost`. Mapa (São Paulo,
zoom 15): 3 oficinas do SAM, **28 estabelecimentos do OpenStreetMap** (losangos; popup
"não cadastrado no SAM" com link para o OSM), tiles do OSM **todos com status 200**
(21 no Chromium, 22 no Firefox) e Referer `https://sam.localhost/`, atribuição "© OpenStreetMap contributors" com link para
`/copyright`. Sem a CA: `net::ERR_CERT_AUTHORITY_INVALID` / `SEC_ERROR_UNKNOWN_ISSUER`.

### 5.3 Overpass

- **Indisponível (falha injetada)**: `status: unavailable` em ~8 ms (recuo ativo), aviso
  "Os estabelecimentos do OpenStreetMap estão indisponíveis no momento. As oficinas
  cadastradas no SAM continuam no mapa.", oficina do SAM listada e no mapa.
- **Indisponível (de verdade)**: durante toda a validação a `overpass-api.de` respondeu
  "502 — at capacity" ou estourou o tempo, e `overpass.private.coffee` /
  `overpass.kumi.systems` também. O staging degradou como esperado.
- **Disponível**: com a instância pública `maps.mail.ru` (lenta: 12–20 s por consulta;
  staging com `SAM_OVERPASS_TIMEOUT_SECONDS=30`), a primeira tentativa recebeu 504 (o
  SAM degradou) e a seguinte trouxe a área de São Paulo: **28 estabelecimentos reais do
  OpenStreetMap junto com as 3 oficinas do SAM**, nos dois navegadores (a segunda
  carga veio do cache por célula). O staging ficou configurado com essa instância.
- **Simulada** (determinística, roda em qualquer máquina):
  `tests/e2e/test_map_openstreetmap.py` em Chromium e Firefox — losangos separados dos
  pinos do SAM, duplicata removida, popup sem funções do SAM, filtros de tipo/texto,
  categoria e "aberto agora", liga/desliga e falha.

### 5.4 Backup e restauração

- Volume `sam-staging_backups` (separado de `sam-staging_pgdata`); arquivos
  `sam-AAAAMMDDTHHMMSSZ.tar.gpg` + `.sha256`, cifrados (frase em
  `~/.local/share/sam-staging/secrets/backup/`).
- Primeiro backup automático na subida (10:51 UTC); próximos às 03h (America/Sao_Paulo);
  antes de cada atualização, pelo `deploy.sh` (11:05, 11:07, 11:10, 11:18 UTC); manuais
  para os ensaios. 9 arquivos no volume ao fim da validação.
- `restore-drill` (be094-3, 18/11/2026 08:08): PostgreSQL 16 isolado (contêiner
  descartável, rede interna, tmpfs) — banco pronto 1,4 s; `sam-restore` (decifrar,
  sha256, `pg_restore` em transação única, contagens e **md5 do conteúdo das 36
  tabelas**, 1 imagem por hash) 0,8 s; API de produção sobre o banco restaurado
  (`check_schema`, `migrate --check`, `/ready/` 200, 4 oficinas no mapa, 1 cliente) 3,3 s;
  **total 5,6 s** (RTO 8 h). Idade do backup no ensaio: 7 s.
- Repetido com a versão final (be094-5, 08:30): 36 tabelas, 368 linhas, md5 das 36, 1
  imagem; banco 1,4 s + restauração 0,9 s + API 3,3 s = **5,6 s**.
- Primeira tentativa (be094-2) **falhou**: `pg_restore` não recriava
  `uq_service_name_normalized` — corrigido pela migration `catalog/0002` (ADR 0025).

### 5.5 Implantação

`deploy/smoke-test.sh` (com `SAM_COMPOSE_OVERRIDE` = loopback): **42/42** verificações —
primeira implantação, imagem sem root, Gunicorn PID 1, HTTPS/HSTS/CSP, mesma origem,
413, SNI desconhecido, cadastro + upload, backup + restauração em banco limpo, SIGTERM,
migration que falha sem derrubar a versão no ar, atualização, rollback e alerta do
monitor com o banco fora do ar (76 s).

### 5.6 Alertas do monitor

- **Rotina de expiração parada**: `jobs` parado às 11:29:08 UTC →
  `[SAM staging] ALERTA — Rotina de expiração (orçamentos, promoções, divulgações): sem
  execução bem-sucedida há 15 min (máximo 15 min)` às 11:43:55; religado às 11:44 →
  `RESOLVIDO … em dia` às 11:44:25 (logger `sam.alerts`; sem webhook configurado no
  staging, o alerta fica no log do monitor).
- **Banco fora do ar**: alerta em 76 s no `smoke-test.sh` (mesma imagem e configuração).

## 6. Limitações

- Volume de dados pequeno (demonstração): o tempo de restauração cresce com o dump;
  repita o ensaio com dados realistas antes de afirmar o RTO para outro volume.
- Execução diária do backup ao longo de vários dias **não observada** (o staging subiu em
  18/11/2026); a regra do agendador é coberta por testes (ADR 0025).
- Overpass pública instável: ver 5.3.
- Sem Let's Encrypt, DNS público, rede externa nem cópia fora do servidor (rclone) — não
  se aplicam a um staging local.
