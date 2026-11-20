#!/usr/bin/env bash
# Funções comuns do backup e da restauração do SAM (BE-090). Carregado por
# sam-backup, sam-restore e sam-backup-loop; não execute sozinho.
#
# Conexão: variáveis padrão da libpq (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE).

: "${BACKUP_DIR:=/backups}"
: "${MEDIA_DIR:=/media}"
: "${SAM_ENVIRONMENT:=produção}"

# Log em JSON, uma linha por evento (mesmo formato dos logs do Django, BE-018).
log() {
    local level=$1 message=$2
    shift 2
    jq -cn --arg time "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" --arg level "$level" \
        --arg message "$message" --arg logger "${SAM_LOGGER:-sam.backup}" \
        '{time: $time, level: $level, logger: $logger, message: $message}' >&2
}

die() {
    log ERROR "$1"
    exit "${2:-1}"
}

require_commands() {
    local missing=()
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
    done
    ((${#missing[@]} == 0)) || die "Ferramentas ausentes: ${missing[*]}"
}

# pg_dump/pg_restore precisam ser da mesma versão principal do servidor: um dump do
# pg_dump 17+ grava `SET transaction_timeout`, que o PostgreSQL 16 não reconhece.
check_server_version() {
    local server client
    server=$(psql -X -At -c "SHOW server_version_num") || die "Banco inacessível (${PGHOST:-local}:${PGPORT:-5432})."
    server=$((server / 10000))
    client=$(pg_dump --version | grep -oE '[0-9]+' | head -1)
    if [[ "$client" != "$server" ]]; then
        die "pg_dump $client × servidor PostgreSQL $server: use as ferramentas da mesma versão (imagem postgres:$server)."
    fi
}

# Conteúdo de cada tabela (BE-094): md5 do conjunto de linhas, sem depender da ordem
# física nem da collation — md5 de cada linha (texto do registro), ordenados em "C" e
# concatenados. O texto do registro depende de configurações da sessão: as mesmas
# (CHECKSUM_SETTINGS) são usadas no backup e na restauração.
CHECKSUM_SETTINGS="SET TIME ZONE 'UTC'; SET DateStyle = 'ISO, YMD'; SET IntervalStyle = 'postgres'; SET extra_float_digits = 1; SET bytea_output = 'hex';"
CHECKSUM_QUERY="SELECT COALESCE(json_object_agg(c.relname, (xpath('/row/h/text()', query_to_xml(format(\$q\$SELECT md5(COALESCE(string_agg(s.h, '' ORDER BY s.h COLLATE \"C\"), '')) AS h FROM (SELECT md5(t::text) AS h FROM public.%I t) s\$q\$, c.relname), false, true, '')))[1]::text ORDER BY c.relname), '{}') FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p');"

# Envia um alerta pelo webhook (JSON com `text` e `content`: Slack, Discord e afins),
# se SAM_ALERT_WEBHOOK_URL estiver definido. Falha do webhook só vira log.
alert() {
    local message="[SAM ${SAM_ENVIRONMENT}] $1"
    log ERROR "$message"
    [[ -n "${SAM_ALERT_WEBHOOK_URL:-}" ]] || return 0
    jq -cn --arg text "$message" '{text: $text, content: $text, source: "sam-backup"}' |
        curl -fsS -m 10 -H 'Content-Type: application/json' --data-binary @- \
            "$SAM_ALERT_WEBHOOK_URL" >/dev/null ||
        log WARNING "Não foi possível enviar o alerta pelo webhook."
}

# Batimento na tabela job_heartbeat (core/0003): o monitor alerta backup velho ou com
# falha. Sem a tabela (banco antigo) ou sem banco, só registra no log.
heartbeat_success() {
    psql -X -q -v ON_ERROR_STOP=1 -v details="$1" >/dev/null 2>&1 <<'SQL' ||
INSERT INTO job_heartbeat (job_name, date_last_run, date_last_success, details)
VALUES ('backup', clock_timestamp(), clock_timestamp(), :'details'::jsonb)
ON CONFLICT (job_name) DO UPDATE
SET date_last_run = EXCLUDED.date_last_run,
    date_last_success = EXCLUDED.date_last_success,
    details = EXCLUDED.details;
SQL
        log WARNING "Não foi possível gravar o batimento do backup."
}

heartbeat_failure() {
    psql -X -q -v ON_ERROR_STOP=1 -v error="${1:0:1000}" >/dev/null 2>&1 <<'SQL' ||
INSERT INTO job_heartbeat (job_name, date_last_run, date_last_failure, last_error)
VALUES ('backup', clock_timestamp(), clock_timestamp(), :'error')
ON CONFLICT (job_name) DO UPDATE
SET date_last_run = EXCLUDED.date_last_run,
    date_last_failure = EXCLUDED.date_last_failure,
    last_error = EXCLUDED.last_error;
SQL
        log WARNING "Não foi possível gravar a falha do backup no banco."
}

# Diretório do GnuPG descartável (não deixa chaves nem trustdb no contêiner).
gpg_home() {
    GNUPGHOME=$(mktemp -d)
    export GNUPGHOME
    chmod 700 "$GNUPGHOME"
}

sha256_of() {
    sha256sum "$1" | cut -d' ' -f1
}
