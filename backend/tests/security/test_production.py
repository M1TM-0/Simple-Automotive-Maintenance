"""BE-085 — Configuração segura de produção e cabeçalhos de segurança.

As settings de produção são lidas num processo separado (`config.settings.prod`
valida tudo na importação), como em `tests/test_settings.py`.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest
from django.core import mail

from tests.test_settings import BACKEND_DIR, STRONG_SECRET_KEY, run_production_settings

PROBE = """
import json
import django
django.setup()
from django.test import Client

client = Client()
out = {}
r = client.get("/api/")
out["http"] = [r.status_code, r.get("Location")]
r = client.get("/api/health/")
out["health_http"] = r.status_code
r = client.get("/api/health/", secure=True)
out["headers"] = {k: r.get(k) for k in (
    "Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options",
    "Referrer-Policy", "Cross-Origin-Opener-Policy")}
r = client.get("/api/auth/me/", secure=True)
cookie = r.cookies.get("csrftoken")
out["csrf_cookie"] = {"secure": bool(cookie["secure"]), "samesite": cookie["samesite"]} if cookie else None
r = client.get("/api/", HTTP_X_FORWARDED_PROTO="https")
out["forwarded"] = r.status_code
print(json.dumps(out))
"""


def _probe(**extra_env):
    result = run_production_settings(
        STRONG_SECRET_KEY, "False", code=PROBE, ALLOWED_HOSTS="testserver", **extra_env
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_check_deploy_has_no_warnings():
    # Ambiente limpo: a sessão de testes não pode mascarar nem causar aviso de produção.
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_ALLOW_ASYNC_UNSAFE"}
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "SECRET_KEY": STRONG_SECRET_KEY,
            "DEBUG": "False",
            "DATABASE_URL": "sqlite:///db.sqlite3",
            "ALLOWED_HOSTS": "sam.exemplo.com.br",
        }
    )
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no issues" in result.stdout


@pytest.mark.parametrize("hosts", ["", "*", "sam.exemplo.com.br,*"])
def test_production_requires_explicit_allowed_hosts(hosts):
    result = run_production_settings(STRONG_SECRET_KEY, "False", ALLOWED_HOSTS=hosts)

    assert result.returncode != 0
    assert "ALLOWED_HOSTS must list" in result.stderr


def test_http_redirects_to_https_and_secure_headers_are_sent():
    out = _probe()

    assert out["http"] == [301, "https://testserver/api/"]
    assert out["health_http"] == 200, "health check fica fora do redirecionamento"
    assert out["headers"] == {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    assert out["csrf_cookie"] == {"secure": True, "samesite": "Lax"}


def test_forwarded_proto_is_trusted_only_behind_the_proxy():
    # Sem a flag, um cliente não forja "já estou em HTTPS" pelo cabeçalho.
    assert _probe()["forwarded"] == 301
    # Atrás do Nginx (que define o cabeçalho), a requisição segue sem laço: /api/ → 404 JSON.
    assert _probe(USE_X_FORWARDED_PROTO="True")["forwarded"] == 404


def test_hsts_preload_is_an_explicit_choice():
    code = (
        "import django; django.setup(); from django.conf import settings as s; "
        "print(s.SECURE_HSTS_PRELOAD, getattr(s, 'SILENCED_SYSTEM_CHECKS', []))"
    )
    off = run_production_settings(STRONG_SECRET_KEY, "False", code=code)
    on = run_production_settings(
        STRONG_SECRET_KEY, "False", code=code, SECURE_HSTS_PRELOAD="True"
    )

    assert off.stdout.strip() == "False ['security.W021']"
    assert on.stdout.strip() == "True []"


# --------------------------------------------- documentação interativa (DEBUG=False)


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/api/schema/", "/api/docs/"])
def test_interactive_docs_are_admin_only_outside_debug(
    url, client_session, api_client, admin_session
):
    assert api_client.get(url).status_code in (401, 403)
    assert client_session.get(url).status_code in (401, 403)
    assert admin_session.get(url).status_code == 200


# ----------------------------------------------- e-mail de redefinição assíncrono


@pytest.mark.django_db(transaction=True)
def test_reset_email_is_sent_outside_the_request(settings, monkeypatch, api_client):
    from apps.core.tests.factories import ClientFactory

    settings.SAM_EMAIL_ASYNC = True
    client = ClientFactory(email="ana@exemplo.com")
    import apps.accounts.emails as emails

    original = emails.send_mail
    done = threading.Event()

    def slow_send(*args, **kwargs):
        time.sleep(0.8)  # SMTP lento
        original(*args, **kwargs)
        done.set()

    monkeypatch.setattr(emails, "send_mail", slow_send)

    started = time.monotonic()
    existing = api_client.post(
        "/api/auth/password-reset/", {"email": client.email}, format="json"
    )
    elapsed_existing = time.monotonic() - started

    started = time.monotonic()
    missing = api_client.post(
        "/api/auth/password-reset/", {"email": "ninguem@exemplo.com"}, format="json"
    )
    elapsed_missing = time.monotonic() - started

    assert existing.status_code == missing.status_code == 204
    assert elapsed_existing < 0.5, "a resposta esperou o envio do e-mail"
    assert abs(elapsed_existing - elapsed_missing) < 0.4
    assert done.wait(5), "o e-mail não foi enviado pela thread"
    assert [m.to for m in mail.outbox] == [[client.email]]
