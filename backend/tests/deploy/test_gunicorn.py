"""BE-088: Gunicorn de produção (gunicorn.conf.py).

* A API real, com `config.settings.prod`, sobe no Gunicorn e responde em
  `/api/health/ready/` com o banco pronto (critério 1 da tarefa).
* SIGTERM (o que o `docker stop` envia ao PID 1) espera a requisição em andamento
  terminar antes de sair (critério 2); acima de `graceful_timeout` ela é cortada.
* O critério "`id -u` ≠ 0" é da imagem: `USER sam` no backend/Dockerfile, conferido
  em tests/deploy/test_artifacts.py e na subida real do CI (deploy-smoke).
"""

import http.client
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from django.db import connection

from tests.test_settings import STRONG_SECRET_KEY

BACKEND = Path(__file__).resolve().parents[2]
CONF = BACKEND / "gunicorn.conf.py"
GUNICORN = Path(sys.executable).with_name("gunicorn")

pytestmark = pytest.mark.deploy


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_listening(port, proc, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"gunicorn saiu: {proc.stdout.read()}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("gunicorn não abriu a porta")


def _start(app, port, **env):
    full_env = {**os.environ, "PYTHONPATH": str(BACKEND), **env}
    full_env.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
    return subprocess.Popen(
        [str(GUNICORN), "--config", str(CONF), "--bind", f"127.0.0.1:{port}", app],
        cwd=BACKEND,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop(proc):
    if proc.poll() is None:
        proc.kill()
        proc.wait(10)


def _load_conf(monkeypatch, **env):
    for key in (
        "GUNICORN_WORKERS",
        "GUNICORN_THREADS",
        "GUNICORN_TIMEOUT",
        "GUNICORN_GRACEFUL_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("sam_gunicorn_conf", CONF)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_config_defaults_match_the_measured_setup(monkeypatch):
    conf = _load_conf(monkeypatch)

    assert conf.worker_class == "gthread" and conf.threads == 8
    assert 1 <= conf.workers <= 4
    assert conf.preload_app is False  # pool do psycopg nasce depois do fork
    assert conf.graceful_timeout >= conf.timeout
    assert conf.keepalive > 4  # o upstream do Nginx fecha antes (keepalive_timeout 4s)


def test_config_reads_the_environment(monkeypatch):
    conf = _load_conf(
        monkeypatch, GUNICORN_WORKERS="7", GUNICORN_THREADS="2", GUNICORN_TIMEOUT="10"
    )

    assert (conf.workers, conf.threads, conf.timeout) == (7, 2, 10)


@pytest.mark.django_db
def test_production_api_answers_ready_under_gunicorn():
    db = connection.settings_dict
    url = f"postgres://{db['USER']}:{db['PASSWORD']}@{db['HOST'] or 'localhost'}:{db['PORT'] or 5432}/{db['NAME']}"
    port = _free_port()
    proc = _start(
        "config.wsgi:application",
        port,
        DJANGO_SETTINGS_MODULE="config.settings.prod",
        SECRET_KEY=STRONG_SECRET_KEY,
        DEBUG="False",
        ALLOWED_HOSTS="sam.exemplo.com.br",
        DATABASE_URL=url,
        USE_X_FORWARDED_PROTO="True",
        SAM_NUM_PROXIES="1",
        GUNICORN_WORKERS="1",
        GUNICORN_THREADS="2",
    )
    try:
        _wait_listening(port, proc)

        def get(path, **headers):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                conn.request(
                    "GET", path, headers={"Host": "sam.exemplo.com.br", **headers}
                )
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        assert get("/api/health/ready/") == (200, b'{"status":"ok"}')
        # Fora do health, HTTP é redirecionado — a não ser que venha do Nginx com https.
        assert get("/api/auth/me/")[0] == 301
        assert get("/api/auth/me/", **{"X-Forwarded-Proto": "https"})[0] == 401
    finally:
        _stop(proc)


def _slow_request(port, seconds, result):
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/slow?{seconds}", timeout=30
        ) as response:
            result["status"], result["body"] = response.status, response.read()
    except Exception as exc:  # noqa: BLE001 — o teste inspeciona o erro
        result["error"] = exc


@pytest.mark.parametrize(
    ("seconds", "graceful", "completes"), [(2, "10", True), (4, "1", False)]
)
def test_sigterm_waits_for_the_request_in_flight(
    tmp_path, seconds, graceful, completes
):
    marker = tmp_path / "in-flight"
    port = _free_port()
    proc = _start(
        "tests.deploy.slow_app:application",
        port,
        SAM_SLOW_APP_MARKER=str(marker),
        GUNICORN_WORKERS="1",
        GUNICORN_GRACEFUL_TIMEOUT=graceful,
    )
    try:
        _wait_listening(port, proc)
        result = {}
        client = threading.Thread(target=_slow_request, args=(port, seconds, result))
        client.start()
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "a requisição lenta não começou"

        started = time.monotonic()
        proc.send_signal(signal.SIGTERM)  # o mesmo que `docker stop` manda ao PID 1
        client.join(30)
        proc.wait(30)
        elapsed = time.monotonic() - started
    finally:
        _stop(proc)

    if completes:
        assert result == {"status": 200, "body": b"terminou"}
        assert elapsed >= seconds - 1  # esperou a requisição, não saiu na hora
    else:
        assert "error" in result  # passou do graceful_timeout: cortada
        assert elapsed < seconds
    assert proc.returncode == 0
