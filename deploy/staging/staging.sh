#!/usr/bin/env bash
# Staging LOCAL do SAM (BE-094) — https://sam.localhost, só nesta máquina.
#
# É a implantação de produção (deploy/compose.prod.yml + deploy/deploy.sh) num projeto
# Docker próprio (`sam-staging`: banco, mídia e backups em volumes próprios, separados do
# desenvolvimento), com o proxy publicado só no loopback e certificado de uma CA local
# (OpenSSL; mesmo papel do mkcert, com restrição de nome: a CA só assina sam.localhost).
# Sem domínio público, hospedagem ou serviço pago.
#
#   staging.sh init            segredos, CA local e certificado (idempotente)
#   staging.sh up [TAG]        build + implantação pelo deploy.sh (backup antes de migrar)
#   staging.sh status          versão no ar e saúde
#   staging.sh seed            dados de demonstração pela API (idempotente)
#   staging.sh check           HTTPS, saúde, mapa, OSM, tiles (verificação rápida)
#   staging.sh backup          backup agora (o diário roda sozinho às BACKUP_HOUR)
#   staging.sh restore-drill   restaura o último backup num PostgreSQL ISOLADO e cronometra
#   staging.sh overpass URL    troca a Overpass da API (ex.: uma URL inválida para o ensaio
#                              de indisponibilidade; "default" volta à pública)
#   staging.sh trust [--install]   como confiar na CA local nos navegadores
#   staging.sh compose ARGS…   docker compose do staging (ps, logs -f api, exec…)
#   staging.sh stop            para os contêineres (volumes preservados)
#
# Estado e segredos FORA do repositório, em $SAM_STAGING_HOME
# (padrão ~/.local/share/sam-staging, 0700): env.staging, ca/, certs/, secrets/backup/,
# deploy-state, demo-accounts.json e drills/ (relatórios dos ensaios de restauração).
# Passo a passo e evidências: backend/docs/STAGING.md.
set -Eeuo pipefail

HERE=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
DEPLOY=$(dirname "$HERE")
REPO=$(dirname "$DEPLOY")
H=${SAM_STAGING_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/sam-staging}
HOST=${SAM_STAGING_HOST:-sam.localhost}
CA="$H/ca/ca.pem"
RTO_SECONDS=$((8 * 3600))  # BE-094: RTO 8 h
RPO_SECONDS=$((24 * 3600)) # BE-094: RPO 24 h

export SAM_PROJECT=sam-staging
export SAM_ENV_FILE="$H/env.staging"
export SAM_STATE_FILE="$H/deploy-state"
export SAM_COMPOSE_OVERRIDE="$HERE/compose.staging.yml"

log() { printf '[staging %s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die() {
    log "ERRO: $*"
    exit 1
}

env_value() { { grep -E "^$1=" "$SAM_ENV_FILE" 2>/dev/null || true; } | tail -n 1 | cut -d= -f2-; }
compose() { "$DEPLOY/compose.sh" "$@"; }
version() { sed -n 's/^CURRENT=//p' "$SAM_STATE_FILE" 2>/dev/null || true; }
https() { curl -sS --max-time 20 --cacert "$CA" "$@"; }  # SEM -k: o certificado é validado

require_init() {
    [[ -f "$SAM_ENV_FILE" && -f "$CA" ]] || die "Rode primeiro: $0 init"
}

# ------------------------------------------------------------------ init
make_ca() {
    [[ -f "$H/ca/ca.key" && -f "$CA" ]] && return 0
    log "Criando a CA local (restrita a $HOST)…"
    openssl req -x509 -new -nodes -newkey rsa:3072 -sha256 -days 825 \
        -keyout "$H/ca/ca.key" -out "$CA" \
        -subj "/O=SAM staging local/CN=SAM staging local CA" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "nameConstraints=critical,permitted;DNS:$HOST" \
        -addext "subjectKeyIdentifier=hash" 2>/dev/null
    chmod 0600 "$H/ca/ca.key"
    chmod 0644 "$CA"
}

make_cert() {
    local leaf="$H/certs/fullchain.pem" key="$H/certs/privkey.pem"
    if [[ -f "$leaf" && -f "$key" ]] &&
        openssl x509 -in "$leaf" -noout -checkend $((30 * 86400)) >/dev/null 2>&1 &&
        openssl verify -CAfile "$CA" "$leaf" >/dev/null 2>&1 &&
        openssl x509 -in "$leaf" -noout -ext subjectAltName 2>/dev/null | grep -q "DNS:$HOST"; then
        return 0
    fi
    log "Emitindo o certificado de $HOST (válido por 397 dias)…"
    local work
    work=$(mktemp -d)
    openssl req -new -nodes -newkey rsa:2048 -sha256 -keyout "$work/key.pem" -out "$work/req.csr" \
        -subj "/CN=$HOST" 2>/dev/null
    cat >"$work/ext.cnf" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$HOST
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
EOF
    openssl x509 -req -sha256 -days 397 -in "$work/req.csr" -CA "$CA" -CAkey "$H/ca/ca.key" \
        -CAcreateserial -CAserial "$H/ca/ca.srl" -extfile "$work/ext.cnf" -out "$work/leaf.pem" 2>/dev/null
    install -m 0644 "$work/leaf.pem" "$leaf"
    install -m 0600 "$work/key.pem" "$key"  # lida pelo master do Nginx (root no contêiner)
    rm -rf "$work"
    openssl verify -CAfile "$CA" "$leaf" >/dev/null || die "Certificado não confere com a CA."
}

cmd_init() {
    umask 077
    install -d -m 0700 "$H" "$H/ca" "$H/certs" "$H/drills"
    # Montado no contêiner de backup (usuário postgres): diretório e frase legíveis por
    # ele; quem protege no host é o $H em 0700.
    install -d -m 0755 "$H/secrets" "$H/secrets/backup"
    if [[ ! -s "$H/secrets/backup/passphrase" ]]; then
        openssl rand -hex 32 >"$H/secrets/backup/passphrase"
    fi
    chmod 0644 "$H/secrets/backup/passphrase"

    if [[ ! -f "$SAM_ENV_FILE" ]]; then
        log "Criando $SAM_ENV_FILE (segredos aleatórios)…"
        cat >"$SAM_ENV_FILE" <<EOF
# SAM — staging LOCAL (gerado por deploy/staging/staging.sh init; não versionar).
SAM_SERVER_NAME=$HOST
SAM_TLS_DIR=$H/certs
SAM_BACKUP_SECRETS_DIR=$H/secrets/backup
SAM_ENVIRONMENT=staging
POSTGRES_DB=sam
POSTGRES_USER=sam
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 48)
SAM_TIME_ZONE=America/Sao_Paulo
LOG_LEVEL=INFO
LOG_FORMAT=json
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
DB_POOL_MAX=5
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=SAM staging <nao-responda@$HOST>
# Backup diário cifrado (RPO 24 h): frase em secrets/backup/passphrase.
BACKUP_HOUR=03
BACKUP_KEEP_DAYS=14
BACKUP_KEEP_MIN=3
BACKUP_PASSPHRASE_FILE=/run/secrets/backup/passphrase
# Estabelecimentos do OpenStreetMap no mapa (Overpass pública; vazio desliga).
SAM_OVERPASS_URL=https://overpass-api.de/api/interpreter
EOF
    fi
    chmod 0600 "$SAM_ENV_FILE"
    make_ca
    make_cert
    log "Pronto. CA: $CA"
    log "Próximo passo: $0 up   (depois: $0 seed, $0 check)"
}

# ------------------------------------------------------------------ up / status / stop
cmd_up() {
    require_init
    make_cert
    command -v docker >/dev/null || die "docker não encontrado."
    docker info >/dev/null 2>&1 || die "Sem acesso ao Docker (grupo docker? rode com 'sg docker' ou faça login de novo)."
    # O certificado da CA local valida o HTTPS nas verificações do deploy.sh.
    CURL_CA_BUNDLE="$CA" "$DEPLOY/deploy.sh" ${1:+--version "$1"}
    log "No ar: https://$HOST/  (CA local: $0 trust)"
}

cmd_status() {
    require_init
    CURL_CA_BUNDLE="$CA" "$DEPLOY/deploy.sh" --status
}

cmd_stop() {
    require_init
    compose stop
}

# ------------------------------------------------------------------ dados de demonstração
cmd_seed() {
    require_init
    python3 "$HERE/seed_demo.py" --base "https://$HOST" --cafile "$CA" --accounts "$H/demo-accounts.json"
}

# ------------------------------------------------------------------ verificação rápida
check() {
    local description=$1
    shift
    if "$@"; then echo "ok    $description"; else
        echo "FALHA $description"
        FAILURES=$((FAILURES + 1))
    fi
}

json_ok() { jq -e "$2" >/dev/null 2>&1 <<<"$1"; }
tls13() {
    openssl s_client -connect 127.0.0.1:443 -servername "$HOST" -CAfile "$CA" -verify_return_error -brief </dev/null 2>&1 |
        grep -q 'Protocol version: TLSv1.3'
}
loopback_only() {  # 80 e 443 escutando, e só em 127.0.0.1 / [::1]
    local port addrs
    for port in 80 443; do
        addrs=$(ss -Hltn "sport = :$port" | awk '{print $4}')
        grep -qE '^(127\.0\.0\.1|\[::1\]):' <<<"$addrs" || return 1
        ! grep -vqE '^(127\.0\.0\.1|\[::1\]):' <<<"$addrs" || return 1
    done
}
osm_tile() {
    curl -sS -o /dev/null -w '%{http_code} %{content_type}' --max-time 15 -e "https://$HOST/" \
        https://tile.openstreetmap.org/15/12139/18592.png | grep -q '^200 image/png'
}

cmd_check() {
    require_init
    FAILURES=0
    local out headers
    check "TLS válido pela CA local (curl sem -k)" https -o /dev/null "https://$HOST/"
    check "TLS 1.3 negociado" tls13
    check "HTTP → HTTPS" test "$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "http://$HOST/map.html")" = "301 https://$HOST/map.html"
    check "portas 80/443 só no loopback" loopback_only
    for path in /api/health/ /api/health/ready/ /api/health/jobs/; do
        check "GET $path → 200" test "$(https -o /dev/null -w '%{http_code}' "https://$HOST$path")" = 200
    done
    headers=$(https -o /dev/null -D - "https://$HOST/map.html")
    check "CSP permite os tiles do OSM" grep -qi 'img-src[^;]*https://tile.openstreetmap.org' <<<"$headers"
    out=$(https "https://$HOST/js/map.js")
    check "map.js com atribuição © OpenStreetMap contributors" grep -q 'OpenStreetMap</a> contributors' <<<"$out"
    check "map.js pede os tiles com Referer de origem" grep -q "referrerPolicy: 'strict-origin-when-cross-origin'" <<<"$out"
    out=$(https "https://$HOST/api/map/points/")
    check "oficinas do SAM no mapa (/api/map/points/: $(jq -r .count <<<"$out" 2>/dev/null))" json_ok "$out" '.count > 0'
    out=$(https "https://$HOST/api/map/external-points/?south=-23.566&west=-46.662&north=-23.556&east=-46.648")
    check "OSM externo responde 200 com status ($(jq -r .status <<<"$out" 2>/dev/null), $(jq -r .count <<<"$out" 2>/dev/null) pontos)" \
        json_ok "$out" '.status | IN("ok","partial","unavailable")'
    check "tile do OSM com Referer da origem → 200 image/png" osm_tile
    ((FAILURES == 0)) && echo "Verificação do staging: tudo certo." || echo "Verificação do staging: $FAILURES falha(s)."
    return $((FAILURES > 0))
}

# ------------------------------------------------------------------ backup
cmd_backup() {
    require_init
    local archive
    archive=$(compose exec -T backup sam-backup | tr -d '\r' | tail -n 1)
    [[ "$archive" == /backups/sam-*.tar.gpg ]] || die "Backup falhou: $archive"
    log "Backup gravado no volume sam-staging_backups: $archive"
    echo "$archive"
}

# ------------------------------------------------------------------ ensaio de restauração
# Restaura o backup mais recente do staging num PostgreSQL 16 NOVO e ISOLADO (contêiner
# descartável, rede interna sem saída, dados em tmpfs), confere tudo (sha256, contagens,
# md5 do conteúdo de cada tabela, imagens) e sobe a API de produção sobre o banco
# restaurado (check_schema + /api/health/ready/). Cronometra cada etapa e grava o
# relatório em $H/drills/. Não toca no banco de staging nem no de desenvolvimento.
now() { date +%s.%N; }
since() { awk -v a="$1" -v b="$(now)" 'BEGIN { printf "%.1f", b - a }'; }

cmd_restore_drill() {
    require_init
    local v archive id net db pw started t report_file
    v=$(version)
    [[ -n "$v" ]] || die "Staging não implantado ($0 up)."
    archive=${1:-$(compose exec -T backup sh -c 'ls -1 /backups/sam-*.tar.gpg 2>/dev/null | sort | tail -n 1' | tr -d '\r')}
    [[ -n "$archive" ]] || die "Nenhum backup no volume sam-staging_backups ($0 backup)."
    id=$(date +%Y%m%dT%H%M%S)
    net="sam-restore-drill-$id"
    db="sam-restore-drill-db-$id"
    pw=$(openssl rand -hex 16)
    # shellcheck disable=SC2064
    trap "docker rm -f '$db' >/dev/null 2>&1 || true; docker network rm '$net' >/dev/null 2>&1 || true" EXIT

    log "Ensaio de restauração: $archive → PostgreSQL isolado ($db)"
    started=$(now)

    # 1. banco novo e isolado
    t=$(now)
    docker network create --internal "$net" >/dev/null
    docker run -d --name "$db" --network "$net" --tmpfs /var/lib/postgresql/data:rw,size=2g \
        -e POSTGRES_USER=sam -e POSTGRES_PASSWORD="$pw" -e POSTGRES_DB=sam_restore \
        postgres:16-bookworm >/dev/null
    for _ in $(seq 1 60); do
        docker exec "$db" pg_isready -U sam -d sam_restore -q 2>/dev/null &&
            docker exec "$db" psql -U sam -d sam_restore -Atqc 'SELECT 1' >/dev/null 2>&1 && break
        sleep 1
    done
    local t_db
    t_db=$(since "$t")

    # 2. sam-restore (decifra, confere sha256, pg_restore em transação única, contagens,
    #    md5 do conteúdo por tabela e imagens)
    t=$(now)
    local restore_out
    restore_out=$(docker run --rm --network "$net" --user 0 \
        -v sam-staging_backups:/backups:ro \
        -v "$H/secrets/backup:/run/secrets/backup:ro" \
        -e PGHOST="$db" -e PGUSER=sam -e PGPASSWORD="$pw" -e PGDATABASE=sam_restore \
        -e BACKUP_PASSPHRASE_FILE=/run/secrets/backup/passphrase -e SAM_ENVIRONMENT=staging-drill \
        "sam-backup:$v" sam-restore "$archive" --media-dir /tmp/restored-media 2>&1) ||
        die "sam-restore falhou: $(tail -n 5 <<<"$restore_out")"
    local t_restore report
    t_restore=$(since "$t")
    report=$(tail -n 1 <<<"$restore_out")
    jq -e . >/dev/null <<<"$report" || die "Relatório do sam-restore ilegível: $report"

    # 3. a API de produção sobe sobre o banco restaurado
    t=$(now)
    local api_env=(--rm --network "$net" --env-file "$SAM_ENV_FILE"
        -e DJANGO_SETTINGS_MODULE=config.settings.prod
        -e "DATABASE_URL=postgres://sam:$pw@$db:5432/sam_restore"
        -e "ALLOWED_HOSTS=$HOST" -e "CSRF_TRUSTED_ORIGINS=https://$HOST" -e CORS_ALLOWED_ORIGINS=
        -e USE_X_FORWARDED_PROTO=True -e SAM_NUM_PROXIES=1 -e SAM_OVERPASS_URL=)
    docker run "${api_env[@]}" "sam-api:$v" python manage.py check_schema >/dev/null ||
        die "check_schema falhou no banco restaurado."
    docker run "${api_env[@]}" "sam-api:$v" python manage.py migrate --check >/dev/null ||
        die "Migrations pendentes no banco restaurado."
    local api_out
    api_out=$(docker run "${api_env[@]}" "sam-api:$v" python -c "
import json, django
django.setup()
from django.test import Client
from apps.accounts.models import Client as C, Workshop as W
r = Client(HTTP_HOST='$HOST', HTTP_X_FORWARDED_PROTO='https').get('/api/health/ready/')
m = Client(HTTP_HOST='$HOST', HTTP_X_FORWARDED_PROTO='https').get('/api/map/points/')
print(json.dumps({'ready': r.status_code, 'map_points': m.json().get('count'), 'clients': C.objects.count(), 'workshops': W.objects.count()}))
" | tail -n 1) || die "A API não respondeu sobre o banco restaurado."
    local t_api
    t_api=$(since "$t")
    [[ "$(jq -r .ready <<<"$api_out")" == 200 ]] || die "/api/health/ready/ ≠ 200 no banco restaurado: $api_out"

    local total created age
    total=$(since "$started")
    created=$(jq -r .restored_from <<<"$report")
    age=$(($(date +%s) - $(date -d "$created" +%s)))
    report_file="$H/drills/drill-$id.json"
    jq -n --arg id "$id" --arg archive "$archive" --arg version "$v" \
        --argjson restore "$report" --argjson api "$api_out" \
        --argjson t_db "$t_db" --argjson t_restore "$t_restore" --argjson t_api "$t_api" \
        --argjson total "$total" --argjson rto "$RTO_SECONDS" \
        --argjson age "$age" --argjson rpo "$RPO_SECONDS" \
        --arg backup_hour "$(env_value BACKUP_HOUR)" \
        '{drill: $id, archive: $archive, image_version: $version, isolated_database: "postgres:16-bookworm (tmpfs, rede interna)",
          seconds: {provision_database: $t_db, restore_and_verify: $t_restore, api_on_restored_db: $t_api, total: $total},
          rto: {target_seconds: $rto, measured_seconds: $total, met: ($total <= $rto)},
          rpo: {target_seconds: $rpo, backup_schedule: ("diário às " + $backup_hour + "h (sam-backup-loop)"),
                backup_age_at_drill_seconds: $age},
          restore_report: $restore, api_on_restored_db: $api}' >"$report_file"
    cat "$report_file"
    log "Ensaio concluído em ${total}s (RTO alvo: ${RTO_SECONDS}s). Relatório: $report_file"
}

# ------------------------------------------------------------------ Overpass (ensaio de falha)
cmd_overpass() {
    require_init
    local url=${1:?uso: $0 overpass URL|default}
    [[ "$url" == default ]] && url=https://overpass-api.de/api/interpreter
    sed -i "s|^SAM_OVERPASS_URL=.*|SAM_OVERPASS_URL=$url|" "$SAM_ENV_FILE"
    log "SAM_OVERPASS_URL=$url — recriando a API…"
    compose up -d --no-deps --wait api >/dev/null
    # Recuo de uma falha anterior não deve mascarar o ensaio (o cache das células fica).
    compose exec -T api python manage.py shell -c \
        "from django.core.cache import cache; cache.delete_many(['sam:overpass:cooldown', 'sam:overpass:backoff'])" >/dev/null
    log "API pronta."
}

# ------------------------------------------------------------------ confiança na CA
cmd_trust() {
    require_init
    if [[ "${1:-}" == --install ]]; then
        command -v certutil >/dev/null || die "certutil não encontrado (pacote nss)."
        local db
        install -d -m 0700 "$HOME/.pki/nssdb"
        [[ -f "$HOME/.pki/nssdb/cert9.db" ]] || certutil -N -d "sql:$HOME/.pki/nssdb" --empty-password
        certutil -A -d "sql:$HOME/.pki/nssdb" -t "C,," -n "SAM staging local CA" -i "$CA"
        log "CA instalada para Chromium/Chrome ($HOME/.pki/nssdb)."
        for db in "$HOME"/.mozilla/firefox/*/cert9.db "$HOME"/.config/mozilla/firefox/*/cert9.db; do
            [[ -f "$db" ]] || continue
            certutil -A -d "sql:$(dirname "$db")" -t "C,," -n "SAM staging local CA" -i "$CA"
            log "CA instalada no perfil do Firefox $(dirname "$db") (feche o Firefox antes)."
        done
        return 0
    fi
    cat <<EOF
CA local do staging: $CA
(restrita por nameConstraints a $HOST: não consegue assinar nenhum outro domínio)

Para os navegadores desta máquina confiarem em https://$HOST/:
  $0 trust --install          Chromium/Chrome (~/.pki/nssdb) e perfis do Firefox (certutil)
ou manualmente:
  Firefox: Configurações → Privacidade e Segurança → Certificados → Ver certificados →
           Autoridades → Importar → $CA → "Confiar nesta CA para identificar sites"
  Chrome/Chromium: chrome://certificate-manager → Certificados locais → Importar
  Sistema (curl, Python): sudo trust anchor --store $CA
Para remover: certutil -D -d sql:\$HOME/.pki/nssdb -n "SAM staging local CA"
Os testes E2E do staging não dependem disso: criam bancos de certificados próprios.
EOF
}

case ${1:-} in
init) cmd_init ;;
up) shift; cmd_up "${1:-}" ;;
status) cmd_status ;;
stop) cmd_stop ;;
seed) cmd_seed ;;
check) cmd_check ;;
backup) cmd_backup ;;
restore-drill) shift; cmd_restore_drill "${1:-}" ;;
overpass) shift; cmd_overpass "${1:-}" ;;
trust) shift; cmd_trust "${1:-}" ;;
compose) shift; require_init; compose "$@" ;;
*) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
