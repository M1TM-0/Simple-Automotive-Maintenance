#!/usr/bin/env bash
# Implantação e atualização do SAM em produção (BE-091; seções 13.3 e 13.4 do backlog).
#
#   ./deploy.sh [--version TAG] [--skip-backup]   implanta (primeira vez ou atualização)
#   ./deploy.sh --rollback                        volta os contêineres para a versão anterior
#   ./deploy.sh --status                          versões registradas e saúde
#
# Ordem:
#   1. pré-checagens (.env.prod, segredos, certificado, cifra do backup, compose válido)
#   2. build das imagens da versão nova (sam-api, sam-proxy, sam-backup :TAG)
#   3. backup (pulado na primeira implantação — banco vazio)
#   4. migrate + createcachetable + check_schema com a imagem NOVA, num contêiner avulso:
#      os contêineres da versão no ar não são tocados. Falhou? Para aqui; nada mudou.
#   5. sobe a versão nova (api, jobs, monitor, proxy, backup)
#   6. confere: /api/health/ready/ e o frontend pelo proxy (HTTPS) e a rotina de
#      expiração rodando com sucesso depois da troca. Falhou? Volta para a anterior.
#   7. registra versão atual/anterior em .deploy-state
#
# Migrations precisam ser compatíveis com a versão anterior (a volta não desfaz o
# schema): convenção em backend/docs/migrations.md. Runbook: backend/docs/RUNBOOK.md.
set -Eeuo pipefail

cd "$(dirname "$(readlink -f "$0")")"

ENV_FILE=${SAM_ENV_FILE:-.env.prod}
export SAM_ENV_FILE=$ENV_FILE  # o compose lê o mesmo arquivo para os contêineres (env_file)
STATE_FILE=${SAM_STATE_FILE:-.deploy-state}
READY_TIMEOUT=${SAM_READY_TIMEOUT:-240}
JOBS_TIMEOUT=${SAM_JOBS_TIMEOUT:-180}

log() { printf '[deploy %s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die() {
    log "ERRO: $*"
    exit 1
}

# SAM_COMPOSE_OVERRIDE: arquivo extra do compose (o staging local usa
# staging/compose.staging.yml para publicar o proxy só no loopback). Vazio em produção.
COMPOSE_FILES=(-f compose.prod.yml)
[[ -n "${SAM_COMPOSE_OVERRIDE:-}" ]] && COMPOSE_FILES+=(-f "$SAM_COMPOSE_OVERRIDE")
compose() { docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" "$@"; }
compose_v() {  # compose_v VERSÃO argumentos…: compose com SAM_VERSION definida
    local version=$1
    shift
    SAM_VERSION=$version compose "$@"
}

env_value() {  # último valor de VAR no .env.prod (sem aspas); vazio se não houver
    { grep -E "^$1=" "$ENV_FILE" 2>/dev/null || true; } | tail -n 1 | cut -d= -f2- |
        sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

read_state() {
    CURRENT=""
    PREVIOUS=""
    if [[ -f "$STATE_FILE" ]]; then
        CURRENT=$(grep -E '^CURRENT=' "$STATE_FILE" | cut -d= -f2-)
        PREVIOUS=$(grep -E '^PREVIOUS=' "$STATE_FILE" | cut -d= -f2-)
    fi
}

write_state() {
    printf 'CURRENT=%s\nPREVIOUS=%s\nDEPLOYED_AT=%s\n' "$1" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$STATE_FILE.tmp"
    mv "$STATE_FILE.tmp" "$STATE_FILE"
}

# ------------------------------------------------------------------ 1. pré-checagens
preflight() {
    command -v docker >/dev/null || die "docker não encontrado."
    command -v curl >/dev/null || die "curl não encontrado (usado na verificação pelo proxy)."
    docker compose version >/dev/null 2>&1 || die "docker compose (v2) não encontrado."
    [[ -f "$ENV_FILE" ]] || die "$ENV_FILE não existe: cp .env.prod.example $ENV_FILE e preencha."
    if [[ "$(stat -c %a "$ENV_FILE")" != 600 ]]; then
        log "AVISO: $ENV_FILE com permissão $(stat -c %a "$ENV_FILE"); recomendado: chmod 600."
    fi

    local var missing=()
    for var in SAM_SERVER_NAME POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD SECRET_KEY; do
        [[ -n "$(env_value "$var")" ]] || missing+=("$var")
    done
    ((${#missing[@]} == 0)) || die "Variáveis vazias em $ENV_FILE: ${missing[*]}"
    [[ "$(env_value POSTGRES_PASSWORD)" =~ ^[A-Za-z0-9]+$ ]] ||
        die "POSTGRES_PASSWORD deve ter só letras e números (vai dentro da DATABASE_URL)."

    SERVER_NAME=$(env_value SAM_SERVER_NAME)
    local tls_dir
    tls_dir=$(env_value SAM_TLS_DIR)
    tls_dir=${tls_dir:-./certs}
    [[ -s "$tls_dir/fullchain.pem" && -s "$tls_dir/privkey.pem" ]] ||
        die "Certificado ausente: $tls_dir/fullchain.pem e privkey.pem (RUNBOOK, seção HTTPS)."

    local secrets_dir key file
    secrets_dir=$(env_value SAM_BACKUP_SECRETS_DIR)
    secrets_dir=${secrets_dir:-./secrets/backup}
    for key in BACKUP_GPG_RECIPIENT_FILE BACKUP_PASSPHRASE_FILE; do
        file=$(env_value "$key")
        [[ -n "$file" ]] || continue
        [[ -s "$secrets_dir/${file#/run/secrets/backup/}" ]] ||
            die "$key aponta para $file, mas $secrets_dir/${file#/run/secrets/backup/} não existe."
        BACKUP_KEY_OK=1
    done
    [[ -n "${BACKUP_KEY_OK:-}" ]] ||
        die "Defina BACKUP_GPG_RECIPIENT_FILE ou BACKUP_PASSPHRASE_FILE (backup cifrado é obrigatório)."

    compose_v preflight config -q || die "compose.prod.yml inválido com $ENV_FILE."
}

default_version() {
    local sha
    sha=$(git -C .. rev-parse --short=12 HEAD 2>/dev/null) || {
        date -u +%Y%m%d%H%M%S
        return
    }
    if [[ -n "$(git -C .. status --porcelain 2>/dev/null)" ]]; then
        log "AVISO: há alterações não commitadas; a versão leva o sufixo -dirty."
        sha="$sha-dirty-$(date -u +%Y%m%d%H%M%S)"
    fi
    echo "$sha"
}

db_psql() {
    # O compose.prod.yml exige SAM_VERSION em toda chamada (imagens da API), mesmo num
    # `exec` no banco: sem ela a interpolação falha antes de qualquer coisa (defeito
    # achado na primeira subida real, BE-094). A versão não importa para o `db`.
    compose_v "${SAM_VERSION:-${CURRENT:-none}}" exec -T db psql -X -At -v ON_ERROR_STOP=1 \
        -U "$(env_value POSTGRES_USER)" -d "$(env_value POSTGRES_DB)" -c "$1"
}

# Volumes nomeados com o dono certo (o primeiro contêiner a montar não decide).
prepare_volumes() {
    local version=$1
    compose_v "$version" run --rm --no-deps --user 0 --entrypoint "" api \
        sh -c 'chown 10001:10001 /app/media && chmod 0755 /app/media' >/dev/null
    compose_v "$version" run --rm --no-deps --user 0 --entrypoint "" proxy \
        sh -c 'chown nginx:10001 /var/log/sam && chmod 2775 /var/log/sam' >/dev/null
    compose_v "$version" run --rm --no-deps --user 0 --entrypoint "" backup \
        sh -c 'chown postgres:postgres /backups && chmod 0750 /backups' >/dev/null
}

# ------------------------------------------------------------------ 6. verificação
https_ok() {  # https_ok CAMINHO: 200 pelo proxy, resolvendo o domínio para esta máquina
    curl -ksSf -o /dev/null --max-time 10 --resolve "$SERVER_NAME:443:127.0.0.1" \
        "https://$SERVER_NAME$1"
}

verify() {
    local since=$1 deadline
    deadline=$((SECONDS + READY_TIMEOUT))
    until https_ok /api/health/ready/ && https_ok /; do
        ((SECONDS < deadline)) || {
            log "/api/health/ready/ ou o frontend não responderam 200 em ${READY_TIMEOUT}s."
            return 1
        }
        sleep 3
    done
    log "API pronta e frontend no ar em https://$SERVER_NAME/"
    if ! curl -sSf -o /dev/null --max-time 10 --resolve "$SERVER_NAME:443:127.0.0.1" "https://$SERVER_NAME/"; then
        log "AVISO: o certificado não foi validado pelo curl (autoassinado? cadeia incompleta?)."
    fi

    deadline=$((SECONDS + JOBS_TIMEOUT))
    until [[ "$(db_psql "SELECT EXISTS (SELECT 1 FROM job_heartbeat WHERE job_name = 'expiration' AND date_last_success >= to_timestamp($since))")" == t ]]; do
        ((SECONDS < deadline)) || {
            log "A rotina de expiração não rodou com sucesso em ${JOBS_TIMEOUT}s depois da troca."
            return 1
        }
        sleep 5
    done
    log "Rotina de expiração em execução (batimento depois da troca)."
}

bring_up() {  # bring_up VERSÃO
    compose_v "$1" up -d --remove-orphans --wait --wait-timeout "$READY_TIMEOUT"
}

# ------------------------------------------------------------------ comandos
deploy() {
    local version=$1 skip_backup=$2 started first
    read_state
    preflight
    version=${version:-$(default_version)}
    started=$(date +%s)
    log "Implantando $version (no ar: ${CURRENT:-nenhuma})"

    log "Build das imagens…"
    compose_v "$version" build --pull api proxy backup || die "Build falhou; nada mudou."

    compose_v "$version" up -d --wait db || die "O banco não ficou saudável."
    prepare_volumes "$version"

    first=$(db_psql "SELECT to_regclass('public.django_migrations') IS NULL") || die "Banco inacessível."
    if [[ "$first" == t ]]; then
        log "Primeira implantação: banco vazio, sem backup; o migrate aplica o init.sql (core/0001)."
    elif [[ "$skip_backup" == 1 ]]; then
        log "AVISO: backup pulado (--skip-backup)."
    else
        log "Backup antes de migrar…"
        compose_v "$version" run --rm --no-deps backup /opt/sam-backup/sam-backup ||
            die "Backup falhou; implantação cancelada (${CURRENT:-nada} continua no ar)."
    fi

    log "Migrations com a imagem nova (a versão no ar continua servindo)…"
    compose_v "$version" run --rm --no-deps api python manage.py migrate --noinput ||
        die "migrate falhou; implantação cancelada — ${CURRENT:-nenhuma versão} continua no ar, schema inalterado (cada migration é atômica)."
    compose_v "$version" run --rm --no-deps api python manage.py createcachetable ||
        die "createcachetable falhou; ${CURRENT:-nenhuma versão} continua no ar."
    compose_v "$version" run --rm --no-deps api python manage.py check_schema ||
        die "O schema não confere com o init.sql; ${CURRENT:-nenhuma versão} continua no ar."

    log "Subindo $version…"
    if bring_up "$version" && verify "$started"; then
        if [[ "$CURRENT" != "$version" ]]; then
            write_state "$version" "$CURRENT"
        else
            write_state "$version" "$PREVIOUS"
        fi
        log "Implantação concluída: $version."
        return 0
    fi

    if [[ -n "$CURRENT" && "$CURRENT" != "$version" ]]; then
        log "A versão nova não ficou pronta: voltando para $CURRENT…"
        if bring_up "$CURRENT" && verify "$started"; then
            die "Implantação de $version desfeita; $CURRENT no ar. Veja os logs: docker compose logs api jobs proxy."
        fi
        die "A volta para $CURRENT também falhou: intervenção manual (RUNBOOK, Incidentes)."
    fi
    die "A primeira implantação não ficou pronta; veja os logs: docker compose -f compose.prod.yml logs."
}

rollback() {
    read_state
    preflight
    [[ -n "$PREVIOUS" ]] || die "Não há versão anterior registrada em $STATE_FILE."
    log "Voltando de ${CURRENT:-?} para $PREVIOUS (o schema não é desfeito)…"
    bring_up "$PREVIOUS" && verify "$(date +%s)" || die "A versão $PREVIOUS não ficou pronta."
    write_state "$PREVIOUS" "$CURRENT"
    log "No ar: $PREVIOUS."
}

status() {
    read_state
    echo "versão no ar: ${CURRENT:-nenhuma}   anterior: ${PREVIOUS:-nenhuma}"
    [[ -f "$ENV_FILE" ]] || return 0
    SERVER_NAME=$(env_value SAM_SERVER_NAME)
    compose_v "${CURRENT:-none}" ps
    https_ok /api/health/ready/ && echo "ready: ok" || echo "ready: FALHOU"
    https_ok /api/health/jobs/ && echo "jobs: ok" || echo "jobs: FALHOU"
}

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
}

MODE=deploy
VERSION=""
SKIP_BACKUP=0
while [[ $# -gt 0 ]]; do
    case $1 in
    --version) VERSION=${2:?}; shift 2 ;;
    --skip-backup) SKIP_BACKUP=1; shift ;;
    --rollback) MODE=rollback; shift ;;
    --status) MODE=status; shift ;;
    -h | --help) usage ;;
    *) usage ;;
    esac
done

[[ -z "$VERSION" || "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || die "Versão inválida: $VERSION"

case $MODE in
deploy) deploy "$VERSION" "$SKIP_BACKUP" ;;
rollback) rollback ;;
status) status ;;
esac
