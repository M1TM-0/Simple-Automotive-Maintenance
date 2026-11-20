#!/usr/bin/env bash
# `docker compose` de produção com a versão que está no ar (lida de .deploy-state).
#   deploy/compose.sh ps
#   deploy/compose.sh logs -f api
#   deploy/compose.sh exec api python manage.py createsuperuser
# Para implantar/atualizar use deploy.sh (ele faz backup, migrate e verificação).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
STATE=${SAM_STATE_FILE:-.deploy-state}
VERSION=${SAM_VERSION:-$(sed -n 's/^CURRENT=//p' "$STATE" 2>/dev/null || true)}
[[ -n "$VERSION" ]] || { echo "Nenhuma versão implantada ($STATE). Use deploy.sh." >&2; exit 1; }
export SAM_VERSION=$VERSION SAM_ENV_FILE=${SAM_ENV_FILE:-.env.prod}
FILES=(-f compose.prod.yml)
[[ -n "${SAM_COMPOSE_OVERRIDE:-}" ]] && FILES+=(-f "$SAM_COMPOSE_OVERRIDE")  # staging local
exec docker compose "${FILES[@]}" --env-file "$SAM_ENV_FILE" "$@"
