from .base import *

DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)

# Em dev, cookies não exigem HTTPS por padrão
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

# CORS explícito para frontend local (nunca wildcard com credenciais)
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
)
