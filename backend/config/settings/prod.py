from django.core.exceptions import ImproperlyConfigured

from .base import *

# Trechos que denunciam uma chave de exemplo (comparação sem diferenciar maiúsculas).
_PLACEHOLDER_MARKERS = (
    "django-insecure-",
    "change_me",
    "changeme",
    "replace-me",
    "coloque",
    "secret_key_here",
    "your-secret",
)


def _is_weak_secret_key(key):
    lowered = key.lower()
    return (
        len(key) < 50
        or len(set(key)) < 5
        or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)
    )


# Validate SECRET_KEY
if not SECRET_KEY or _is_weak_secret_key(SECRET_KEY):
    raise ImproperlyConfigured(
        "SECRET_KEY must be configured with a secure production secret "
        "(at least 50 characters, varied, and not a placeholder). "
        'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )


# Validate DEBUG
if DEBUG:
    raise ImproperlyConfigured("DEBUG must be False in production.")


# Hosts explícitos (BE-085): nunca vazio nem curinga.
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must list the production host names explicitly (no '*')."
    )


# Validate database
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL must be configured in production.")

# Produção: mesma origem via proxy recomendada; CORS só se explicitamente configurado
# Nunca permitir wildcard com credenciais
if env.bool("CORS_ALLOW_ALL_ORIGINS", default=False):
    raise ImproperlyConfigured("CORS_ALLOW_ALL_ORIGINS must be False in production.")

# Cache compartilhado entre os workers (limites de taxa e bloqueio de login, BE-033).
# Padrão: tabela no próprio PostgreSQL (`manage.py createcachetable`).
_PROCESS_LOCAL_CACHES = (
    "django.core.cache.backends.locmem.LocMemCache",
    "django.core.cache.backends.dummy.DummyCache",
)
_cache_backend = env(
    "CACHE_BACKEND", default="django.core.cache.backends.db.DatabaseCache"
)
if _cache_backend in _PROCESS_LOCAL_CACHES:
    raise ImproperlyConfigured(
        "CACHE_BACKEND must be shared between processes in production "
        "(e.g. django.core.cache.backends.db.DatabaseCache or a Redis cache)."
    )
CACHES = {
    "default": {
        "BACKEND": _cache_backend,
        "LOCATION": env("CACHE_LOCATION", default="sam_cache"),
    }
}

# ------------------------------------------------------------------------------
# HTTPS, cookies e cabeçalhos (BE-085). `manage.py check --deploy --fail-level WARNING`
# passa sem avisos (testado em tests/security/test_production.py e no CI).
# Decisões em backend/docs/seguranca/producao.md.
# ------------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# Health check do orquestrador/compose bate em HTTP dentro da rede interna.
SECURE_REDIRECT_EXEMPT = [r"^api/health/"]

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# CSRF_COOKIE_HTTPONLY continua False: o frontend lê `csrftoken` para o X-CSRFToken.

# HSTS: 1 ano, inclusive subdomínios. Preload fica DESLIGADO por padrão: entrar na
# lista de preload dos navegadores é difícil de desfazer e é decisão do dono do
# domínio (ligue com SECURE_HSTS_PRELOAD=True quando o domínio estiver pronto).
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
if not SECURE_HSTS_PRELOAD:
    SILENCED_SYSTEM_CHECKS = ["security.W021"]  # preload desligado de propósito (acima)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Atrás do Nginx (DP-22, BE-089), que termina o TLS e define X-Forwarded-Proto.
# Sem isto e com SECURE_SSL_REDIRECT, toda requisição repassada pelo proxy em HTTP
# entraria em laço de redirecionamento.
if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# E-mail de redefinição enviado fora da requisição: a resposta leva o mesmo tempo
# exista ou não o e-mail (BE-032/BE-085). Ver apps/accounts/services.py.
SAM_EMAIL_ASYNC = env.bool("SAM_EMAIL_ASYNC", default=True)
