#!/usr/bin/env bash
# Prepara o ambiente de DESENVOLVIMENTO (P-17): cria os arquivos .env que faltam,
# com senha do banco e SECRET_KEY aleatórias. Nunca sobrescreve um .env existente.
#   ./setup.sh && docker compose up --build
# Produção usa outro arquivo e outro roteiro: deploy/.env.prod e deploy/deploy.sh
# (backend/docs/RUNBOOK.md).
set -euo pipefail
cd "$(dirname "$0")"

random_hex() { python3 -c "import secrets; print(secrets.token_hex($1))"; }

create_from_example() {  # create_from_example DESTINO MODELO
    local target=$1 example=$2
    if [[ -f "$target" ]]; then
        echo "$target já existe (mantido)."
        return 1
    fi
    [[ -f "$example" ]] || { echo "Erro: $example não encontrado." >&2; exit 1; }
    cp "$example" "$target"
    chmod 600 "$target"
    echo "$target criado a partir de $example."
}

if create_from_example .env .env.example; then
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(random_hex 24)/" .env
fi

if create_from_example backend/.env backend/.env.example; then
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(random_hex 48)/" backend/.env
fi

echo "Pronto. Suba com: docker compose up --build"
echo "API: http://localhost:8000/api/health/  ·  Frontend: http://localhost:5500/"
