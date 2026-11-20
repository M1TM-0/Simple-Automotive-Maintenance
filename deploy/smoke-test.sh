#!/usr/bin/env bash
# Ensaio da implantação com Docker de verdade (BE-088…BE-092; job deploy-smoke do CI).
# Também serve de roteiro em staging. NÃO rode num servidor de produção: o projeto de
# teste (sam-smoke) é apagado no fim, com os volumes.
#
#   deploy/smoke-test.sh
#
# Domínio localhost com certificado autoassinado; nada do .env.prod real é usado.
set -Eeuo pipefail

cd "$(dirname "$(readlink -f "$0")")"
REPO=$(cd .. && pwd)

export SAM_PROJECT=sam-smoke
WORK=$(mktemp -d)
export SAM_ENV_FILE="$WORK/env.prod"
export SAM_STATE_FILE="$WORK/deploy-state"
FAILING_MIGRATION="$REPO/backend/apps/core/migrations/0099_smoke_falha.py"
# SAM_COMPOSE_OVERRIDE (opcional): ex. staging/compose.staging.yml publica o proxy só
# no loopback — use numa máquina de desenvolvimento (o deploy.sh lê a mesma variável).
COMPOSE=(docker compose -f compose.prod.yml ${SAM_COMPOSE_OVERRIDE:+-f "$SAM_COMPOSE_OVERRIDE"} --env-file "$SAM_ENV_FILE")
CURL=(curl -ksS --max-time 20 --resolve localhost:443:127.0.0.1 --resolve localhost:80:127.0.0.1)
FAILURES=0

pass() { echo "ok    $*"; }
fail() {
    echo "FALHA $*"
    FAILURES=$((FAILURES + 1))
}
check() {
    local description=$1
    shift
    if "$@"; then pass "$description"; else fail "$description"; fi
}
step() { printf '\n== %s\n' "$*"; }

cleanup() {
    rm -f "$FAILING_MIGRATION"
    if ((FAILURES > 0)); then
        "${COMPOSE[@]}" ps -a || true
        "${COMPOSE[@]}" logs --tail 80 || true
    fi
    SAM_VERSION=cleanup "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

http_code() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$@" || true; }
db_sql() { "${COMPOSE[@]}" exec -T db psql -X -At -U sam -d "${2:-sam}" -c "$1"; }
current_image() { docker inspect -f '{{.Config.Image}}' "$("${COMPOSE[@]}" ps -q api)"; }

# ------------------------------------------------------------------ configuração de teste
step "Configuração (certificado autoassinado, segredos aleatórios)"
mkdir -p "$WORK/certs" "$WORK/secrets"
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost" \
    -keyout "$WORK/certs/privkey.pem" -out "$WORK/certs/fullchain.pem" 2>/dev/null
chmod 0644 "$WORK/certs/privkey.pem"
openssl rand -hex 32 >"$WORK/secrets/passphrase"
chmod 0644 "$WORK/secrets/passphrase"
DB_PASSWORD=$(openssl rand -hex 16)
cat >"$SAM_ENV_FILE" <<EOF
SAM_SERVER_NAME=localhost
SAM_TLS_DIR=$WORK/certs
SAM_BACKUP_SECRETS_DIR=$WORK/secrets
SAM_ENVIRONMENT=smoke
POSTGRES_DB=sam
POSTGRES_USER=sam
POSTGRES_PASSWORD=$DB_PASSWORD
SECRET_KEY=$(openssl rand -hex 48)
GUNICORN_WORKERS=2
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
BACKUP_PASSPHRASE_FILE=/run/secrets/backup/passphrase
EOF
chmod 600 "$SAM_ENV_FILE"

# ------------------------------------------------------------------ BE-091 primeira implantação
step "Primeira implantação (deploy.sh)"
check "deploy.sh --version smoke1 (primeira implantação)" ./deploy.sh --version smoke1
export SAM_VERSION=smoke1

check "check_schema: objetos do init.sql (23 tabelas, 3 views, 16 triggers, 26 funções)" \
    "${COMPOSE[@]}" exec -T api python manage.py check_schema
check "rotina de expiração com batimento recente (/api/health/jobs/ 200)" \
    test "$(http_code https://localhost/api/health/jobs/)" = 200
for service in api jobs proxy; do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$("${COMPOSE[@]}" ps -q "$service")")
    check "contêiner $service saudável ($status)" test "$status" = healthy
done

# ------------------------------------------------------------------ BE-088 imagem
step "Imagem da API"
uid=$("${COMPOSE[@]}" exec -T api id -u | tr -d '\r')
check "processo da API sem root (id -u = $uid)" test "$uid" != 0
pid1=$("${COMPOSE[@]}" exec -T api cat /proc/1/cmdline | tr '\0' ' ')
check "Gunicorn é o PID 1 ($pid1)" grep -q gunicorn <<<"$pid1"

# ------------------------------------------------------------------ BE-089 proxy
step "Proxy: HTTPS, mesma origem, cabeçalhos, limites"
check "https://localhost/ carrega o frontend" test "$(http_code https://localhost/)" = 200
headers=$("${CURL[@]}" -o /dev/null -D - https://localhost/map.html)
check "CSP no frontend" grep -qi '^content-security-policy: default-src' <<<"$headers"
check "HSTS no frontend" grep -qi '^strict-transport-security: max-age=31536000' <<<"$headers"
config_js=$("${CURL[@]}" https://localhost/js/config.js)
check "config.js de produção (API na mesma origem)" grep -q 'API_BASE: window.location.origin' <<<"$config_js"
redirect=$("${CURL[@]}" -o /dev/null -w '%{http_code} %{redirect_url}' http://localhost/map.html)
check "HTTP → HTTPS ($redirect)" test "$redirect" = "301 https://localhost/map.html"
me_headers=$("${CURL[@]}" -o /dev/null -D - -w '%{http_code}' https://localhost/api/auth/me/)
check "GET /api/auth/me/ sem sessão → 401" grep -q '401$' <<<"$me_headers"
check "sem cabeçalho CORS (mesma origem)" bash -c '! grep -qi "^access-control-allow-origin" <<<"$1"' _ "$me_headers"
check "estáticos do Django (/static/)" test "$(http_code https://localhost/static/core/default-profile.png)" = 200
check "mídia só com extensão de imagem (/media/x.txt → 404)" test "$(http_code https://localhost/media/x.txt)" = 404
check "SNI desconhecido recusado" bash -c '! curl -ksS --max-time 10 --resolve outro.exemplo:443:127.0.0.1 -o /dev/null https://outro.exemplo/ 2>/dev/null'
big=$(head -c 18000000 /dev/zero | "${CURL[@]}" -X POST --data-binary @- -H 'Content-Type: application/json' \
    -w ' %{http_code}' https://localhost/api/auth/login/ || true)
check "corpo acima do limite → 413 em JSON" grep -q '"detail".* 413$' <<<"$big"

step "Escrita pela mesma origem: cadastro, CSRF e upload de foto"
JAR="$WORK/cookies"
"${CURL[@]}" -c "$JAR" -o /dev/null https://localhost/api/auth/me/
csrf() { awk '$6 == "csrftoken" {print $7}' "$JAR" | tail -n 1; }
code=$("${CURL[@]}" -b "$JAR" -c "$JAR" -o "$WORK/register.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' -H "X-CSRFToken: $(csrf)" -H 'Origin: https://localhost' \
    --data '{"role":"client","email":"smoke@exemplo.com","password":"SenhaForte123","name":"Cliente Smoke"}' \
    https://localhost/api/auth/register/)
check "POST /api/auth/register/ → 201 ($code)" test "$code" = 201
"${COMPOSE[@]}" exec -T api python -c "import io,sys; from PIL import Image; b=io.BytesIO(); Image.new('RGB',(64,64),(200,0,0)).save(b,'JPEG'); sys.stdout.buffer.write(b.getvalue())" >"$WORK/photo.jpg"
code=$("${CURL[@]}" -b "$JAR" -c "$JAR" -o "$WORK/me.json" -w '%{http_code}' -X PATCH \
    -H "X-CSRFToken: $(csrf)" -H 'Origin: https://localhost' -F "photo_profile=@$WORK/photo.jpg;type=image/jpeg" \
    https://localhost/api/me/)
check "PATCH /api/me/ com foto → 200 ($code)" test "$code" = 200
photo=$(jq -r '.photo_profile // .user.photo_profile // empty' "$WORK/me.json")
check "foto com URL https da mesma origem ($photo)" grep -q '^https://localhost/media/' <<<"$photo"
check "foto servida pelo Nginx a partir do volume da API" test "$(http_code "$photo")" = 200

# ------------------------------------------------------------------ BE-090 backup e restauração
step "Backup e restauração em banco limpo"
archive=$("${COMPOSE[@]}" exec -T backup sam-backup | tr -d '\r' | tail -n 1)
check "backup cifrado gravado ($archive)" grep -q '^/backups/sam-.*\.tar\.gpg$' <<<"$archive"
check "batimento do backup gravado" test "$(db_sql "SELECT date_last_success IS NOT NULL FROM job_heartbeat WHERE job_name = 'backup'")" = t
db_sql "CREATE DATABASE sam_restore" >/dev/null
report=$("${COMPOSE[@]}" run -T --rm --no-deps --user 0 -e PGDATABASE=sam_restore backup \
    sam-restore latest --media-dir /tmp/restored-media | tail -n 1 || true)
check "sam-restore conferiu contagens e imagens ($report)" test "$(jq -r '.media_files' <<<"$report" 2>/dev/null)" = 1
check "a API sobe sobre o banco restaurado (check_schema)" \
    "${COMPOSE[@]}" run -T --rm --no-deps -e "DATABASE_URL=postgres://sam:$DB_PASSWORD@db:5432/sam_restore" api \
    python manage.py check_schema
ready_restored=$("${COMPOSE[@]}" run -T --rm --no-deps -e "DATABASE_URL=postgres://sam:$DB_PASSWORD@db:5432/sam_restore" api \
    python -c "import django; django.setup(); from django.test import Client; from apps.accounts.models import Client as C; print(Client(HTTP_HOST='localhost').get('/api/health/ready/').status_code, C.objects.filter(email='smoke@exemplo.com').count())" | tail -n 1)
check "restaurado: /api/health/ready/ 200 e o cliente do ensaio presente ($ready_restored)" test "$ready_restored" = "200 1"

# ------------------------------------------------------------------ BE-088 parada controlada
step "docker stop da API (SIGTERM → encerramento controlado)"
api_container=$("${COMPOSE[@]}" ps -q api)
"${COMPOSE[@]}" stop api >/dev/null
check "Gunicorn saiu sozinho no SIGTERM (código 0, não 137)" test "$(docker inspect -f '{{.State.ExitCode}}' "$api_container")" = 0
"${COMPOSE[@]}" up -d --wait api >/dev/null

# ------------------------------------------------------------------ BE-091 migration que falha
step "Atualização com migration que falha"
cat >"$FAILING_MIGRATION" <<'EOF'
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0003_job_heartbeat")]
    operations = [migrations.RunSQL("SELECT 1 / 0", reverse_sql=migrations.RunSQL.noop)]
EOF
check "deploy.sh --version smoke2 é recusado" bash -c '! ./deploy.sh --version smoke2'
rm -f "$FAILING_MIGRATION"
check "a versão anterior continua no ar ($(current_image))" test "$(current_image)" = sam-api:smoke1
check "e respondendo (/api/health/ready/ 200)" test "$(http_code https://localhost/api/health/ready/)" = 200
check "schema intacto (migration não registrada)" test "$(db_sql "SELECT count(*) FROM django_migrations WHERE name = '0099_smoke_falha'")" = 0

step "Atualização normal e volta de versão"
check "deploy.sh --version smoke3" ./deploy.sh --version smoke3
check "smoke3 no ar" test "$(current_image)" = sam-api:smoke3
check "deploy.sh --rollback" ./deploy.sh --rollback
check "smoke1 de volta no ar" test "$(current_image)" = sam-api:smoke1

# ------------------------------------------------------------------ BE-092 monitor
step "Monitor: tudo em ordem e alerta com o banco fora do ar"
check "monitor --once sem falhas" "${COMPOSE[@]}" exec -T monitor python manage.py monitor --once
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
started=$(date +%s)
"${COMPOSE[@]}" stop db >/dev/null
alerted=""
while (($(date +%s) - started < 150)); do
    if "${COMPOSE[@]}" logs --since "$since" monitor 2>/dev/null | grep -q 'ALERTA — Banco de dados indisponível'; then
        alerted=$(($(date +%s) - started))
        break
    fi
    sleep 5
done
check "alerta de banco indisponível em até 2 min (${alerted:-nenhum}s)" test -n "$alerted" -a "${alerted:-999}" -le 120
"${COMPOSE[@]}" start db >/dev/null
for _ in $(seq 1 30); do
    [[ "$(http_code https://localhost/api/health/ready/)" == 200 ]] && break
    sleep 3
done
check "a API se recupera sozinha depois do banco voltar" test "$(http_code https://localhost/api/health/ready/)" = 200

printf '\n%s\n' "$( ((FAILURES == 0)) && echo 'Ensaio de implantação: tudo certo.' || echo "Ensaio de implantação: $FAILURES falha(s).")"
exit $((FAILURES > 0))
