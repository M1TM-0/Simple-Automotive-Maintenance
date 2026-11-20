# syntax=docker/dockerfile:1
#
# Imagens de produção do SAM (BE-088 e BE-089). Contexto de build: RAIZ do repositório,
# porque a migration core/0001 lê database/init.sql e o proxy serve frontend/:
#
#   docker build -f backend/Dockerfile --target api   -t sam-api   .
#   docker build -f backend/Dockerfile --target proxy -t sam-proxy .
#
# Estágios: deps (venv com as dependências pinadas) → app (código + init.sql +
# collectstatic) → proxy (Nginx com o frontend e os estáticos) e api (Gunicorn, usuário
# sem privilégios). `api` é o último estágio: é o alvo padrão.
# O deploy (deploy/compose.prod.yml, deploy/deploy.sh) constrói os dois alvos.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG NGINX_IMAGE=nginx:1.28-alpine

# ------------------------------------------------------------------ dependências
FROM ${PYTHON_IMAGE} AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Só as dependências de execução (base.txt, versões exatas); nada de pytest/ruff/playwright.
COPY backend/requirements/base.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# ------------------------------------------------------------------ aplicação
FROM ${PYTHON_IMAGE} AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    SAM_INIT_SQL_PATH=/app/database/init.sql \
    MEDIA_ROOT=/app/media

# Usuário fixo (uid/gid 10001): o volume de mídia e o diretório de logs do Nginx usam
# esse número (deploy/compose.prod.yml).
RUN groupadd --system --gid 10001 sam \
    && useradd --system --uid 10001 --gid sam --home-dir /app --shell /usr/sbin/nologin sam

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

# Código e init.sql pertencem ao root: o processo da API não consegue alterá-los.
COPY backend/ /app/
COPY database/init.sql /app/database/init.sql

# collectstatic na construção: a imagem já sai com os estáticos (admin, DRF), que o
# estágio `proxy` copia. As settings de produção exigem segredos de verdade na
# importação; aqui basta a base com uma chave descartável (nada é assinado no build).
RUN SECRET_KEY=collectstatic-build-only DJANGO_SETTINGS_MODULE=config.settings.base \
        python manage.py collectstatic --noinput \
    && install -d -o sam -g sam -m 0755 /app/media \
    && python -m compileall -q /app/apps /app/config

# ------------------------------------------------------------------ proxy (BE-089)
FROM ${NGINX_IMAGE} AS proxy

# Sem o default.conf da imagem; a configuração do SAM vem do template (envsubst do
# entrypoint oficial troca ${SAM_SERVER_NAME}).
# /var/www/media é o ponto de montagem do volume de mídia (gravado pela API, uid 10001).
# Com o volume ainda vazio, o Docker copia para ele o dono deste diretório a cada
# montagem: root aqui deixava o volume root e todo upload dava 500 (achado na primeira
# subida real, BE-094). O compose também monta com `nocopy`.
RUN rm -f /etc/nginx/conf.d/default.conf \
    && install -d -o nginx -g 10001 -m 2775 /var/log/sam \
    && install -d -m 0755 /var/www/certbot /etc/nginx/certs \
    && install -d -o 10001 -g 10001 -m 0755 /var/www/media

COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/templates/ /etc/nginx/templates/
COPY deploy/nginx/snippets/ /etc/nginx/snippets/
COPY frontend/ /usr/share/nginx/sam/frontend/
# Mesma origem (DP-21): API_BASE = origem da página, sem mexer na lógica do api.js.
COPY deploy/nginx/config.prod.js /usr/share/nginx/sam/frontend/js/config.js
COPY --from=app /app/staticfiles/ /usr/share/nginx/sam/static/

# O envsubst do entrypoint oficial só troca variáveis SAM_* (as do Nginx, como $host,
# ficam intactas).
ENV SAM_SERVER_NAME=localhost \
    NGINX_ENVSUBST_FILTER=^SAM_

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --start-interval=2s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

# ------------------------------------------------------------------ API (BE-088)
FROM app AS api

USER sam:sam

EXPOSE 8000

# Liveness (sem banco). A prontidão (/api/health/ready/) é conferida pelo deploy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]

# Forma exec: o Gunicorn é o PID 1 e recebe o SIGTERM do `docker stop` (encerramento
# controlado; ver gunicorn.conf.py e stop_grace_period no compose).
STOPSIGNAL SIGTERM
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "config.wsgi:application"]
