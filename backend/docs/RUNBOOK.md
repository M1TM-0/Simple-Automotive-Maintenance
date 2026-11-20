# SAM — Runbook de implantação e operação (BE-093)

Para quem vai **subir, atualizar e manter** o SAM em produção. Cada passo foi escrito para
ser seguido em um servidor limpo, sem ajuda. Decisões por trás: ADRs 0001, 0004, 0021 e
0022 (`backend/docs/adr/`); segurança: `backend/docs/seguranca/producao.md`.

> Comandos a partir da raiz do repositório no servidor. `deploy/compose.sh` é o
> `docker compose` de produção já com o arquivo de variáveis e a versão no ar.

## 1. O que roda

```
             Internet ──443/80──▶ proxy (Nginx: TLS, frontend, /static, /media)
                                     │ /api/ e /admin/ (mesma origem)
                                     ▼
   monitor ──────────────▶ api (Django + Gunicorn, usuário 10001) ──▶ db (PostgreSQL 16)
   (alertas)                         ▲                                     ▲   ▲
   jobs (expiração 60 s, lembretes 1 h) ───────────────────────────────────┘   │
   backup (diário 03h, cifrado, cópia fora do servidor) ───────────────────────┘
```

| Serviço | Imagem | Volumes | Porta |
|---|---|---|---|
| `db` | `postgres:16-bookworm` | `pgdata` | só interna |
| `api` | `sam-api:<versão>` (`backend/Dockerfile`, alvo `api`) | `media` | 8000 interna |
| `jobs` | `sam-api:<versão>` | — | — |
| `monitor` | `sam-api:<versão>` | `nginx_logs`, `media` e `backups` (leitura) | — |
| `proxy` | `sam-proxy:<versão>` (alvo `proxy`) | `media` (leitura), `nginx_logs`, certificados | **80, 443** |
| `backup` | `sam-backup:<versão>` (`deploy/backup/`) | `backups`, `media` (leitura), segredos | — |

Arquivos: `deploy/compose.prod.yml`, `deploy/deploy.sh`, `deploy/compose.sh`,
`deploy/.env.prod.example`, `deploy/nginx/`, `deploy/backup/`, `deploy/smoke-test.sh`.

## 2. Pré-requisitos do servidor

- Linux x86-64 com **Docker Engine ≥ 25** e o plugin **Compose v2**, `git`, `curl`,
  `openssl`. Sugestão para começar: 2 vCPU, 4 GB de RAM, 40 GB de disco (banco + mídia +
  14 backups locais).
- DNS do domínio (ex.: `sam.exemplo.com.br`) apontando para o servidor; portas 80 e 443
  abertas; nada mais exposto (o banco não publica porta).
- Relógio sincronizado (NTP): o batimento das rotinas e a validade dos orçamentos dependem dele.

## 3. Primeira implantação

1. **Código**
   ```bash
   git clone <repositório> sam && cd sam
   ```
2. **Variáveis**
   ```bash
   cp deploy/.env.prod.example deploy/.env.prod && chmod 600 deploy/.env.prod
   python3 -c "import secrets; print(secrets.token_hex(32))"      # POSTGRES_PASSWORD
   python3 -c "import secrets; print(secrets.token_urlsafe(64))"  # SECRET_KEY
   ```
   Preencha `SAM_SERVER_NAME`, `POSTGRES_PASSWORD` (só letras e números), `SECRET_KEY`,
   o SMTP (`EMAIL_*`, `DEFAULT_FROM_EMAIL`) e os alertas (`SAM_ALERT_WEBHOOK_URL` e/ou
   `SAM_ALERT_EMAILS`). O arquivo nunca vai para o git (`.gitignore`) nem para as imagens.
3. **Chave do backup** — gere o par **fora do servidor** (a chave privada nunca fica lá):
   ```bash
   gpg --quick-gen-key "SAM Backup <backup@sam.exemplo.com.br>" future-default default never
   gpg --armor --export backup@sam.exemplo.com.br > backup.pub.asc
   gpg --armor --export-secret-keys backup@sam.exemplo.com.br > backup.key.asc   # cofre!
   ```
   No servidor: `mkdir -p deploy/secrets/backup && chmod 700 deploy/secrets` e copie
   `backup.pub.asc` para `deploy/secrets/backup/` (legível pelo uid 999 do contêiner de
   backup: `chmod 644`). Cópia fora do servidor (recomendada): configure um remoto do
   rclone (`rclone config` em qualquer máquina), salve o `rclone.conf` em
   `deploy/secrets/backup/rclone.conf` e defina `BACKUP_RCLONE_REMOTE=nome:pasta`.
   Alternativa sem par de chaves: `BACKUP_PASSPHRASE_FILE` com uma frase guardada no cofre.
4. **Certificado TLS** (DP-22). Let's Encrypt, com o servidor ainda sem nada na porta 80:
   ```bash
   docker run --rm -p 80:80 -v "$PWD/deploy/letsencrypt:/etc/letsencrypt" certbot/certbot \
     certonly --standalone -d sam.exemplo.com.br --email ops@exemplo.com --agree-tos -n
   mkdir -p deploy/certs
   cp -L deploy/letsencrypt/live/sam.exemplo.com.br/{fullchain,privkey}.pem deploy/certs/
   ```
   (Certificado da instituição: coloque a cadeia completa em `deploy/certs/fullchain.pem`
   e a chave em `deploy/certs/privkey.pem`.) Renovação: seção 9.
5. **Implantar**
   ```bash
   deploy/deploy.sh
   ```
   Ele confere a configuração, constrói as imagens (versão = commit), sobe o banco,
   aplica o `init.sql` pela migration `core/0001` (banco vazio: sem backup), roda
   `check_schema` (23 tabelas, 3 views, 16 triggers, 26 funções e o catálogo semeado:
   62 serviços, 11 categorias), sobe tudo e espera `/api/health/ready/` pelo HTTPS e a
   primeira execução da rotina de expiração. Saída esperada no fim:
   `Implantação concluída: <versão>.`
6. **Conferir**
   ```bash
   deploy/deploy.sh --status                                   # ready: ok / jobs: ok
   deploy/compose.sh exec api python manage.py check_schema
   deploy/compose.sh exec monitor python manage.py monitor --once
   curl -I https://sam.exemplo.com.br/                         # 200 + HSTS + CSP
   curl -I http://sam.exemplo.com.br/                          # 301 → https
   ```
7. **Administrador** (moderação, ADR 0003):
   `deploy/compose.sh exec api python manage.py createsuperuser` → entre em
   `https://<domínio>/admin/`.
8. **Pontos de interesse** (opcional, ADR 0010 — fonte e licença a definir):
   ```bash
   docker cp pontos.geojson "$(deploy/compose.sh ps -q api)":/tmp/pontos.geojson
   deploy/compose.sh exec api python manage.py import_pois --file /tmp/pontos.geojson --source osm-2026-11 --dry-run
   deploy/compose.sh exec api python manage.py import_pois --file /tmp/pontos.geojson --source osm-2026-11
   ```
9. **Primeiro backup e ensaio de restauração** (seção 7) e **teste dos alertas** (seção 8).
10. **Monitor externo**: cadastre `https://<domínio>/api/health/ready/` e
    `https://<domínio>/api/health/jobs/` num serviço de uptime (verificação a cada 1 min)
    e, se usar `SAM_MONITOR_PING_URL`, o "dead man's switch" (alerta se o servidor todo cair).
11. Registre o resultado em `backend/docs/ACEITE.md`.

## 4. Variáveis

O modelo comentado é `deploy/.env.prod.example`. O compose fixa o que não pode variar em
produção (`DEBUG=False` via `config.settings.prod`, `USE_X_FORWARDED_PROTO=True`,
`SAM_NUM_PROXIES=1`, mesma origem, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` derivados de
`SAM_SERVER_NAME`). `config/settings/prod.py` recusa subir com `SECRET_KEY` fraca, `DEBUG`
ligado, `ALLOWED_HOSTS` vazio/curinga ou cache local.

Mapa (BE-094, ADR 0024): `SAM_OVERPASS_URL` (instância pública da Overpass; vazio
desliga a camada do OpenStreetMap), `SAM_OVERPASS_TIMEOUT_SECONDS`,
`SAM_OVERPASS_CACHE_SECONDS`, `SAM_OVERPASS_MAX_REQUESTS_PER_MINUTE` e
`THROTTLE_EXTERNAL_MAP`. O contêiner `api` precisa de saída HTTPS para a Overpass; sem
ela o mapa mostra só o SAM. Tiles: `SAM.config.MAP_TILES` no `config.prod.js` + CSP.

Dimensionamento: conexões ao banco = `GUNICORN_WORKERS × DB_POOL_MAX` (4 × 10) + `jobs`
e `monitor` (2 cada) + backup/migrate; mantenha abaixo de `max_connections=100`.

## 5. Atualizar a versão

```bash
git pull && deploy/deploy.sh                # ou: deploy/deploy.sh --version v1.2.0
```

Ordem (seção 13.4 do backlog): build → **backup** → `migrate` com a imagem nova num
contêiner avulso (a versão no ar continua servindo) → `createcachetable` →
`check_schema` → troca de versão → `/api/health/ready/` + frontend pelo HTTPS → rotina de
expiração rodando com sucesso depois da troca.

- **Migration falhou** → a implantação para; a versão anterior continua no ar e o schema
  fica como estava (cada migration é atômica). Corrija e implante de novo.
- **Versão nova não ficou pronta** → o script volta sozinho para a anterior e sai com erro.
- **Voltar à mão**: `deploy/deploy.sh --rollback` (troca os contêineres; **não** desfaz
  migrations — por isso elas precisam ser compatíveis com a versão anterior:
  `backend/docs/migrations.md`).
- A troca da API leva alguns segundos (uma réplica): o Nginx responde 502 nesse intervalo.
  Prefira horários de pouco uso.
- Imagens antigas ficam no servidor para a volta; limpe de vez em quando:
  `docker image ls 'sam-*'` e `docker image rm sam-api:<versão-velha> …`.

## 6. Rotinas (`jobs`)

`run_expiration_jobs --loop --interval 60 --reminders-interval 3600`: expira orçamentos,
promoções e divulgações vencidos, ativa divulgações pagas, marca estornos e envia os
lembretes de manutenção (a cada 1 h). Cada execução grava o batimento em `JOB_HEARTBEAT`
(`expiration`, `maintenance_reminders`) e toca `/tmp/sam-jobs.alive` (HEALTHCHECK).

```bash
deploy/compose.sh ps jobs                                    # healthy?
curl -s https://<domínio>/api/health/jobs/                   # {"status":"ok"}
deploy/compose.sh exec db psql -U sam -d sam -c "SELECT * FROM job_heartbeat"
deploy/compose.sh exec jobs python manage.py run_expiration_jobs   # uma execução à mão
```

## 7. Backup e restauração (BE-090)

- **Quando**: todo dia às `BACKUP_HOUR` (03h no fuso `SAM_TIME_ZONE`). Se não houve
  backup bem-sucedido desde a última ocorrência desse horário (contêiner parado às 03h,
  primeira subida), roda assim que puder; falhou, tenta de novo em 1 h. Intervalo entre
  backups ≤ 24 h (ADR 0025). Antes de cada atualização o `deploy.sh` faz um também.
- **O quê**: `sam-AAAAMMDDTHHMMSSZ.tar.gpg` com `pg_dump -Fc`, a mídia, o hash de cada
  imagem e um manifesto com a contagem de linhas **e o md5 do conteúdo** de cada tabela
  **no mesmo snapshot** do dump. Ao lado: `.sha256`.
- **Onde**: volume `backups` (14 dias, no mínimo 3 arquivos) e, com rclone, fora do
  servidor (30 dias).
- **RPO 24 h, RTO 8 h** (ADR 0025; decisão do responsável no BE-094). Uma imagem enviada
  durante a cópia pode ficar de fora (a mídia é copiada logo depois do dump). Ensaio
  medido no staging local: restauração conferida + API no ar em 5,6 s (base pequena;
  `backend/docs/STAGING.md`).
- **Falha** → batimento `backup` com erro, alerta pelo webhook e pelo monitor.

Backup à mão: `deploy/compose.sh exec backup sam-backup`.

### Restaurar em ambiente limpo (ensaio mensal — registre em `ACEITE.md`)

Num servidor de staging com o mesmo repositório e a **chave privada** do backup:

```bash
deploy/deploy.sh --version ensaio                     # sobe a pilha com banco vazio
deploy/compose.sh exec db psql -U sam -d postgres -c "CREATE DATABASE sam_restore"
mkdir -p deploy/secrets/backup && cp backup.key.asc deploy/secrets/backup/
# copie o arquivo do backup para o volume `backups` (rclone copy … ou docker cp)
deploy/compose.sh run --rm --user 0 \
  -e PGDATABASE=sam_restore -e BACKUP_GPG_PRIVATE_KEY_FILE=/run/secrets/backup/backup.key.asc \
  backup sam-restore latest --media-dir /tmp/restored-media
```

(Chave privada com senha: acrescente `-e BACKUP_GPG_PRIVATE_KEY_PASSPHRASE_FILE=…`.)
O `sam-restore` confere o hash do arquivo, do dump e da mídia, restaura numa transação
única e compara, para cada tabela, **a contagem e o md5 do conteúdo** com o manifesto;
sai com erro se algo divergir. Depois, confira que a API sobe sobre o banco restaurado:

```bash
deploy/compose.sh run --rm -e DATABASE_URL=postgres://sam:<senha>@db:5432/sam_restore api \
  python manage.py check_schema
```

### Restaurar em produção (desastre)

Servidor novo (ou banco perdido): restaure **antes** de implantar — o `sam-restore` só
grava em banco e mídia vazios.

1. Siga a seção 3 até o passo 4 (código, `.env.prod` com os **mesmos** `POSTGRES_*`,
   segredos, certificado) e coloque a chave privada em `deploy/secrets/backup/`.
2. Suba só o banco e construa a imagem de backup:
   ```bash
   SAM_VERSION=restauracao deploy/compose.sh up -d --wait db
   SAM_VERSION=restauracao deploy/compose.sh build backup
   ```
3. Traga o backup para o volume `backups` (do remoto: `rclone copy remoto:pasta/<arquivo> …`
   montando o volume, ou `docker cp`) e restaure banco **e** mídia (volume `sam_media`):
   ```bash
   SAM_VERSION=restauracao deploy/compose.sh run --rm --user 0 -v sam_media:/restore-media \
     -e BACKUP_GPG_PRIVATE_KEY_FILE=/run/secrets/backup/backup.key.asc \
     backup sam-restore latest --media-dir /restore-media
   ```
   (Chave privada com senha: `BACKUP_GPG_PRIVATE_KEY_PASSPHRASE_FILE`.)
4. `deploy/deploy.sh --skip-backup` (aplica só as migrations que o código tiver a mais) e
   confira `--status` e `monitor --once`. Registre o incidente e o RTO medido.

Banco corrompido no mesmo servidor: pare a escrita (`deploy/compose.sh stop proxy jobs
api`), restaure num banco novo (`CREATE DATABASE sam_novo` + `-e PGDATABASE=sam_novo`),
troque `POSTGRES_DB=sam_novo` no `.env.prod` e rode `deploy/deploy.sh --skip-backup`; o
banco antigo fica para análise.

## 8. Monitoramento e alertas (BE-092)

O serviço `monitor` (`manage.py monitor --loop --interval 30`) verifica:

| Verificação | Alerta quando | Tempo até o alerta |
|---|---|---|
| `db` banco | não responde | 2 falhas seguidas (≤ ~80 s) |
| `api` prontidão | `/api/health/ready/` ≠ 200 (com o banco no ar) | 2 falhas seguidas |
| `job:expiration` | sem sucesso há > 15 min, ou a última execução falhou | próximo ciclo |
| `job:maintenance_reminders` | sem sucesso há > 3 h, ou falhou | próximo ciclo |
| `job:backup` | sem sucesso há > 26 h, ou falhou | próximo ciclo |
| `http:errors` | > 5% de 5xx nas rotas `/api/` em 5 min (≥ 20 requisições) | próximo ciclo |
| `http:latency` | p95 > 1 s nas rotas `/api/` em 5 min | próximo ciclo |
| `db:connections` | > 80% de `max_connections` | próximo ciclo |
| `db:deadlocks` | deadlock novo (`pg_stat_database`) | próximo ciclo |
| `db:locks` | sessão esperando lock há > 60 s | próximo ciclo |
| `disk:*` | < 10% livre em mídia, backups ou logs | próximo ciclo |

Canais: log `sam.alerts` (sempre), `SAM_ALERT_WEBHOOK_URL` (JSON com `text`/`content`) e
`SAM_ALERT_EMAILS`. Cada problema alerta uma vez, repete a cada hora enquanto durar e
manda "RESOLVIDO" quando volta. Limites ajustáveis no `.env.prod` (`SAM_MONITOR_*`).

```bash
deploy/compose.sh exec monitor python manage.py monitor --once    # estado agora
deploy/compose.sh logs --since 1h monitor | grep ALERTA
```

**Testar os alertas** (staging, ou produção em horário combinado):
`deploy/compose.sh stop db` → em até 2 min chega "ALERTA — Banco de dados indisponível";
`deploy/compose.sh start db` → "RESOLVIDO". `deploy/compose.sh stop jobs` por 20 min →
alerta da rotina de expiração.

**Logs**: JSON em `docker logs` (Django: `request_id` igual ao `X-Request-ID` do Nginx;
segredos mascarados). Acesso do Nginx também em `/var/log/sam/access-AAAA-MM-DD.jsonl`
(volume `nginx_logs`; sem query string), apagados depois de 180 dias
(`SAM_ACCESS_LOG_RETENTION_DAYS`; Marco Civil da Internet, art. 15). O PostgreSQL registra
esperas de lock, deadlocks e consultas acima de 1 s (sem os valores dos parâmetros).

## 9. Segredos e certificados

| O quê | Como trocar | Efeito |
|---|---|---|
| `SECRET_KEY` | novo valor no `.env.prod` + `deploy/deploy.sh` | derruba todas as sessões e invalida tokens de redefinição em aberto |
| `POSTGRES_PASSWORD` | `deploy/compose.sh exec db psql -U sam -d sam -c "ALTER ROLE sam PASSWORD '<nova>'"`, depois o `.env.prod` + `deploy/deploy.sh --skip-backup` | o volume do banco guarda a senha antiga até o `ALTER ROLE` |
| SMTP / webhook | `.env.prod` + `deploy/deploy.sh` | — |
| Chave do backup | novo par GPG; troque a pública em `deploy/secrets/backup/` | **guarde a privada antiga** enquanto existirem backups cifrados com ela (30 dias fora do servidor) |
| Certificado Let's Encrypt | renovar a cada ~60 dias (cron abaixo) | — |

Renovação (cron diário no servidor, projeto compose `sam` → volume `sam_certbot_www`):

```bash
docker run --rm -v sam_certbot_www:/var/www/certbot -v "$PWD/deploy/letsencrypt:/etc/letsencrypt" \
  certbot/certbot renew --webroot -w /var/www/certbot -q \
&& cp -L deploy/letsencrypt/live/sam.exemplo.com.br/{fullchain,privkey}.pem deploy/certs/ \
&& deploy/compose.sh exec proxy nginx -s reload
```

Vazou um segredo? Troque-o já (tabela acima), revise `sam.audit` e os logs de acesso, e
registre o incidente.

## 10. Incidentes

| Sintoma | Verifique | Ação |
|---|---|---|
| Site fora / 502 | `deploy/compose.sh ps`, `logs --tail 100 api proxy` | API reiniciando: veja o erro (variável faltando, banco); `deploy/deploy.sh --rollback` se começou depois de uma atualização |
| `Banco de dados indisponível` | `logs db`, disco (`df -h`) | `deploy/compose.sh start db`; a API reconecta sozinha (pool com verificação de conexão) |
| Rotina de expiração parada | `ps jobs`, `logs jobs`, `job_heartbeat.last_error` | `deploy/compose.sh restart jobs`; erro de banco → seção acima |
| Backup falhou | `logs backup`, `job_heartbeat` (`backup`) | causa comum: chave/remote; rode `deploy/compose.sh exec backup sam-backup` e acompanhe |
| Muitos 5xx / lentidão | `logs api`, `monitor --once`, `db:locks` | consulta travada: `SELECT pid, wait_event_type, query FROM pg_stat_activity` e `pg_cancel_backend(pid)`; aumente `GUNICORN_WORKERS` se a CPU sobrar |
| Disco cheio | `docker system df`, volumes | apague imagens antigas, reduza `BACKUP_KEEP_DAYS`, confira a cópia fora do servidor |
| Login de todos bloqueado (429) | `logs api` com `auth.lockout` | confira `SAM_NUM_PROXIES=1` (sem ele todos teriam o IP do Nginx) |

Ensaio cronometrado num PostgreSQL **isolado** (contêiner descartável, rede interna,
tmpfs), com a API de produção subindo sobre o banco restaurado: no staging local,
`deploy/staging/staging.sh restore-drill` (relatório JSON com o tempo de cada etapa, a
idade do backup e a comparação com RPO/RTO). Num servidor, o mesmo roteiro está no
script (`cmd_restore_drill`).

> **Backups anteriores à migration `catalog/0002` não restauram:** o `pg_restore` não
> recria o índice `uq_service_name_normalized` (função sem schema + `search_path` vazio do
> dump; ADR 0025). A produção ainda não tinha sido implantada; os únicos backups assim são
> os primeiros do staging local (18/11/2026), que podem ser descartados.

## 11. Ensaio completo (staging e CI)

`deploy/smoke-test.sh` faz, com Docker de verdade e certificado autoassinado: primeira
implantação, HTTPS/HSTS/CSP, HTTP → HTTPS, mesma origem (cadastro e foto pelo proxy),
API sem root, parada controlada, backup + restauração em banco limpo com a API subindo
sobre ele, migration que falha sem derrubar a versão no ar, atualização e volta de
versão e alerta com o banco fora do ar. Roda no CI (job `deploy-smoke`) e pode ser
repetido em staging (usa o projeto `sam-smoke` e apaga os volumes dele no fim — **nunca
rode no servidor de produção**). Numa máquina de desenvolvimento, publique só no
loopback: `SAM_COMPOSE_OVERRIDE=$PWD/deploy/staging/compose.staging.yml
deploy/smoke-test.sh` (pare antes o proxy do staging local, que usa as mesmas portas).

**Staging local** (sem servidor, sem domínio): `deploy/staging/staging.sh` sobe esta mesma
implantação em `https://sam.localhost`, só no loopback, com CA local — passo a passo,
verificações e evidências em `backend/docs/STAGING.md` (ADR 0026).
