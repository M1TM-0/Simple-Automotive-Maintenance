import os
import secrets
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
STRONG_SECRET_KEY = secrets.token_urlsafe(64)


def run_production_settings(
    secret_key, debug, code="import django; django.setup()", **extra_env
):
    env = os.environ.copy()

    env.update(
        {
            "SECRET_KEY": secret_key,
            "DEBUG": debug,
            "DATABASE_URL": "sqlite:///db.sqlite3",
            "ALLOWED_HOSTS": "sam.exemplo.com.br",
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            **extra_env,
        }
    )

    return subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_production_rejects_missing_secret_key():
    result = run_production_settings("", "False")

    assert result.returncode != 0
    assert "SECRET_KEY must be configured" in result.stderr


def test_production_rejects_debug_enabled():
    result = run_production_settings(STRONG_SECRET_KEY, "True")

    assert result.returncode != 0
    assert "DEBUG must be False" in result.stderr


def test_production_accepts_valid_settings():
    result = run_production_settings(STRONG_SECRET_KEY, "False")

    assert result.returncode == 0, result.stderr


def test_production_rejects_placeholder_secret_key():
    # texto de exemplo do backend/.env.example
    result = run_production_settings(
        "COLOQUE_SUA_CHAVE_SECRETA_AQUI" + "a1B2c3D4" * 4, "False"
    )

    assert result.returncode != 0
    assert "SECRET_KEY must be configured" in result.stderr


def test_production_rejects_short_secret_key():
    result = run_production_settings("abc123", "False")

    assert result.returncode != 0
    assert "SECRET_KEY must be configured" in result.stderr


def test_production_rejects_low_variety_secret_key():
    result = run_production_settings("x" * 60, "False")

    assert result.returncode != 0
    assert "SECRET_KEY must be configured" in result.stderr


def test_production_enables_https_hardening_by_default():
    result = run_production_settings(
        STRONG_SECRET_KEY,
        "False",
        code=(
            "import django; django.setup(); from django.conf import settings as s; "
            "print(s.SECURE_SSL_REDIRECT, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, "
            "s.SECURE_HSTS_SECONDS > 0, s.SECURE_PROXY_SSL_HEADER)"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True True True True None"


def test_production_trusts_forwarded_proto_only_when_enabled():
    result = run_production_settings(
        STRONG_SECRET_KEY,
        "False",
        code=(
            "import django; django.setup(); from django.conf import settings as s; "
            "print(s.SECURE_PROXY_SSL_HEADER)"
        ),
        USE_X_FORWARDED_PROTO="True",
    )

    assert result.returncode == 0, result.stderr
    assert "HTTP_X_FORWARDED_PROTO" in result.stdout


def test_production_uses_a_shared_cache_by_default():
    """Limites de taxa/bloqueio de login precisam valer entre os workers (BE-033)."""
    result = run_production_settings(
        STRONG_SECRET_KEY,
        "False",
        code=(
            "import django; django.setup(); from django.conf import settings as s; "
            "print(s.CACHES['default']['BACKEND'])"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "django.core.cache.backends.db.DatabaseCache"


def test_production_rejects_process_local_cache():
    result = run_production_settings(
        STRONG_SECRET_KEY,
        "False",
        CACHE_BACKEND="django.core.cache.backends.locmem.LocMemCache",
    )

    assert result.returncode != 0
    assert "CACHE_BACKEND must be shared" in result.stderr
