"""Gunicorn da API do SAM em produção (BE-088).

Lido pela imagem (`gunicorn --config /app/gunicorn.conf.py config.wsgi:application`).
Tudo é ajustável por variável de ambiente; os padrões são os da medição do ADR 0023
(workers gthread com 8 threads; p95 de 11,5 ms com 200 usuários em polling).

Dimensionamento: cada processo tem o próprio pool do psycopg (`DB_POOL_MAX`, padrão
10). Conexões da API = GUNICORN_WORKERS × DB_POOL_MAX; some `jobs` e `monitor` (2 cada)
e mantenha a soma abaixo do `max_connections` do PostgreSQL (100 no compose de
produção) com folga para backup, migrations e acesso administrativo.

Encerramento controlado: no SIGTERM (`docker stop`) o mestre para de aceitar conexões
e espera até `graceful_timeout` segundos as requisições em andamento terminarem. O
`stop_grace_period` do compose precisa ser maior que isso (lá: 45 s).
"""

import multiprocessing
import os


def _int(name, default):
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# Padrão: 2 × núcleos + 1, limitado a 4 (o que o ADR 0023 mediu sem o banco ser gargalo).
workers = _int("GUNICORN_WORKERS", min(2 * multiprocessing.cpu_count() + 1, 4))
worker_class = "gthread"
threads = _int("GUNICORN_THREADS", 8)

# Requisição que passar disto é abortada (o worker é reciclado). O Nginx espera um
# pouco mais (proxy_read_timeout 35 s) para devolver o erro do Gunicorn, não o dele.
timeout = _int("GUNICORN_TIMEOUT", 30)
graceful_timeout = _int("GUNICORN_GRACEFUL_TIMEOUT", 30)
# Maior que o keepalive_timeout do upstream no Nginx (4 s): quem fecha a conexão
# ociosa é o Nginx, nunca o Gunicorn no meio de um reaproveitamento (evita 502).
keepalive = _int("GUNICORN_KEEPALIVE", 5)

# Recicla os processos de tempos em tempos (vazamentos de memória de bibliotecas);
# o jitter evita que todos reiniciem juntos.
max_requests = _int("GUNICORN_MAX_REQUESTS", 2000)
max_requests_jitter = _int("GUNICORN_MAX_REQUESTS_JITTER", 200)

# Sem preload: o pool de conexões é criado em cada processo, depois do fork.
preload_app = False

# Arquivo de batimento dos workers em memória (no Docker, /tmp pode ser overlay lento).
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None

# Logs: erros do Gunicorn no stderr; o acesso já é registrado pelo Nginx (JSON, com
# latência) — ligue GUNICORN_ACCESS_LOG=- para ver também aqui.
errorlog = "-"
accesslog = os.environ.get("GUNICORN_ACCESS_LOG") or None
loglevel = os.environ.get(
    "GUNICORN_LOG_LEVEL", os.environ.get("LOG_LEVEL", "info")
).lower()
capture_output = True

proc_name = "sam-api"


def when_ready(server):
    pool_max = _int("DB_POOL_MAX", 10)
    server.log.info(
        "SAM API pronta: %s workers × %s threads; até %s conexões no banco (pool %s/processo)",
        server.cfg.workers,
        server.cfg.threads,
        server.cfg.workers * pool_max,
        pool_max,
    )


control_socket_disable = True
