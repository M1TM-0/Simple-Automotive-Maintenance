from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env("SECRET_KEY", default="")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    # Local apps
    "apps.accounts.apps.AccountsConfig",
    "apps.attendances.apps.AttendancesConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.chat.apps.ChatConfig",
    "apps.core.apps.CoreConfig",
    "apps.moderation.apps.ModerationConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.promotions.apps.PromotionsConfig",
    "apps.reviews.apps.ReviewsConfig",
    "apps.vehicles.apps.VehiclesConfig",
    "apps.workshops.apps.WorkshopsConfig",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.RequestSizeLimitMiddleware",  # 413 antes de ler o corpo (BE-086)
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASE_URL = env("DATABASE_URL", default="")

DATABASES = {
    "default": env.db_url_config(
        DATABASE_URL or "postgres://sam:sam@localhost:5432/sam"
    ),
}

DATABASES["default"]["ATOMIC_REQUESTS"] = False

if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"].setdefault("OPTIONS", {})["pool"] = {
        "min_size": env.int("DB_POOL_MIN", default=2),
        "max_size": env.int("DB_POOL_MAX", default=10),
        "timeout": env.int("DB_POOL_TIMEOUT", default=10),
    }
    # Com pool, o Django testa a conexão ao tirá-la do pool (ConnectionPool.check_connection)
    # quando CONN_HEALTH_CHECKS está ligado (BE-091): depois de um reinício do PostgreSQL
    # (manutenção, troca de imagem) as conexões mortas são trocadas sem virar 500.
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool("DB_POOL_CHECK", default=True)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = env("SAM_TIME_ZONE", default="America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

if not MEDIA_ROOT.is_absolute():
    MEDIA_ROOT = BASE_DIR / MEDIA_ROOT

MEDIA_URL = env("MEDIA_URL", default="/media/")

# CORS / CSRF
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5500"],
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[],
)

CORS_ALLOW_CREDENTIALS = True
try:
    from corsheaders.defaults import default_headers

    CORS_ALLOW_HEADERS = list(default_headers) + ["x-csrftoken"]
except Exception:
    CORS_ALLOW_HEADERS = [
        "accept",
        "authorization",
        "content-type",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
    ]

# Email
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:5500")
# Envia o e-mail de redefinição numa thread, sem segurar a resposta (produção: True).
SAM_EMAIL_ASYNC = env.bool("SAM_EMAIL_ASYNC", default=False)

# Session / Cookies
SESSION_COOKIE_AGE = env.int(
    "SESSION_COOKIE_AGE",
    default=1209600,
)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_HTTPONLY = False  # frontend lê csrftoken
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"  # 403 em JSON nas rotas /api/

# SAM initialization
_sam_init_sql_path = env("SAM_INIT_SQL_PATH", default="")

SAM_INIT_SQL_PATH = (
    Path(_sam_init_sql_path)
    if _sam_init_sql_path
    else BASE_DIR.parent / "database" / "init.sql"
)

if not SAM_INIT_SQL_PATH.is_absolute():
    SAM_INIT_SQL_PATH = BASE_DIR / SAM_INIT_SQL_PATH

# Images
SAM_IMAGE_MAX_BYTES = env.int("SAM_IMAGE_MAX_BYTES", default=5 * 1024 * 1024)
SAM_IMAGE_MAX_DIMENSION = env.int("SAM_IMAGE_MAX_DIMENSION", default=4096)
SAM_DEFAULT_PROFILE_IMAGE = "default-profile.png"

# Tamanho das requisições (BE-086): 413 pelo Content-Length (RequestSizeLimitMiddleware).
# JSON e formulários sem arquivo: 1 MB. Multipart: até 3 fotos no limite + 1 MB de campos.
SAM_MAX_BODY_BYTES = env.int("SAM_MAX_BODY_BYTES", default=1024 * 1024)
SAM_MAX_UPLOAD_BYTES = env.int(
    "SAM_MAX_UPLOAD_BYTES", default=3 * SAM_IMAGE_MAX_BYTES + 1024 * 1024
)
DATA_UPLOAD_MAX_MEMORY_SIZE = SAM_MAX_BODY_BYTES  # parte sem arquivo de um corpo
FILE_UPLOAD_MAX_MEMORY_SIZE = (
    SAM_IMAGE_MAX_BYTES  # acima disto o upload vai para arquivo temporário
)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
DATA_UPLOAD_MAX_NUMBER_FILES = 10

# Divulgação paga (DP-09, BE-064): preço calculado pelo servidor = diárias × valor.
# Pagamento é confirmado manualmente pelo admin (BE-076); não há gateway.
SAM_ADVERTISING_PRICE_PER_DAY = env("SAM_ADVERTISING_PRICE_PER_DAY", default="10.00")

# Lembrete de manutenção preventiva (BE-077, DP-05): avisa quando faltar no máximo
# este percentual do intervalo em km (10 → intervalo de 10.000 km avisa a 1.000 km).
SAM_MAINTENANCE_REMINDER_PERCENT = env.int(
    "SAM_MAINTENANCE_REMINDER_PERCENT", default=10
)

# Estabelecimentos externos do mapa: OpenStreetMap pela Overpass API (BE-094, ADR 0010).
# URL vazia desliga (o mapa mostra só o SAM). Instâncias públicas sem custo:
# https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances
# Política de uso: cache (CACHE_SECONDS), orçamento por minuto e recuo depois de falha.
SAM_OVERPASS = {
    "URL": env("SAM_OVERPASS_URL", default="https://overpass-api.de/api/interpreter"),
    "TIMEOUT_SECONDS": env.float("SAM_OVERPASS_TIMEOUT_SECONDS", default=12),
    "QUERY_TIMEOUT_SECONDS": env.int("SAM_OVERPASS_QUERY_TIMEOUT_SECONDS", default=10),
    "CACHE_SECONDS": env.int("SAM_OVERPASS_CACHE_SECONDS", default=24 * 3600),
    "MAX_CELLS": env.int("SAM_OVERPASS_MAX_CELLS", default=16),
    "MAX_REQUESTS_PER_MINUTE": env.int(
        "SAM_OVERPASS_MAX_REQUESTS_PER_MINUTE", default=10
    ),
    "BACKOFF_SECONDS": env.int("SAM_OVERPASS_BACKOFF_SECONDS", default=60),
    "MAX_BACKOFF_SECONDS": env.int("SAM_OVERPASS_MAX_BACKOFF_SECONDS", default=900),
    "USER_AGENT": env(
        "SAM_OVERPASS_USER_AGENT",
        default="SAM-Simple-Automotive-Maintenance/1.0 (projeto academico)",
    ),
}

# REST framework
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "apps.core.renderers.SamJSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.AccountSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.SamPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.sam_exception_handler",
    "COERCE_DECIMAL_TO_STRING": True,
    "UNICODE_JSON": True,
    "NON_FIELD_ERRORS_KEY": "non_field_errors",
    # Proxies confiáveis à frente da API (BE-089). Atrás do Nginx: 1 — o IP do cliente
    # (limites de taxa, bloqueio de login, auditoria) vem do X-Forwarded-For que o Nginx
    # reescreve. Sem proxy: 0 — só REMOTE_ADDR. Nunca deixe vazio (None): o DRF passaria
    # a confiar no X-Forwarded-For enviado pelo próprio cliente e qualquer um contornaria
    # os limites por IP trocando o cabeçalho (defeito corrigido na Fase 7).
    "NUM_PROXIES": env.int("SAM_NUM_PROXIES", default=0),
    # Limites por view (BE-033): ver apps/core/throttles.py.
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", default="5/min"),  # por IP + perfil + e-mail
        "register": env("THROTTLE_REGISTER", default="10/min"),  # por IP
        "reset": env("THROTTLE_RESET", default="5/min"),  # por IP + e-mail
        "message": env(
            "THROTTLE_MESSAGE", default="30/min"
        ),  # envio no chat, por usuário
        "polling": env(
            "THROTTLE_POLLING", default="120/min"
        ),  # leituras periódicas, por usuário
        "external_map": env(
            "THROTTLE_EXTERNAL_MAP", default="60/min"
        ),  # OSM no mapa, por IP
    },
}

# Bloqueio progressivo do login após falhas repetidas (BE-033).
# THRESHOLD falhas do mesmo IP+conta (ou ACCOUNT_THRESHOLD da mesma conta, de
# qualquer IP) bloqueiam por BASE_SECONDS; cada nova falha dobra, até MAX_SECONDS.
SAM_LOGIN_LOCKOUT = {
    "THRESHOLD": env.int("LOGIN_LOCKOUT_THRESHOLD", default=5),
    "ACCOUNT_THRESHOLD": env.int("LOGIN_LOCKOUT_ACCOUNT_THRESHOLD", default=20),
    "BASE_SECONDS": env.int("LOGIN_LOCKOUT_BASE_SECONDS", default=60),
    "MAX_SECONDS": env.int("LOGIN_LOCKOUT_MAX_SECONDS", default=900),
    "WINDOW_SECONDS": env.int("LOGIN_LOCKOUT_WINDOW_SECONDS", default=3600),
}

# Cache dos limites de taxa e bloqueios. Dev/teste: memória local.
# Produção exige cache compartilhado entre processos (ver prod.py).
CACHES = {
    "default": {
        "BACKEND": env(
            "CACHE_BACKEND", default="django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": env("CACHE_LOCATION", default="sam-local"),
    }
}

# Batimento das rotinas (BE-092): idade máxima, em segundos, da última execução
# bem-sucedida antes do alerta. Expiração roda a cada 60 s (alerta com 15 min parada,
# seção 13.5 do backlog); lembretes a cada 1 h; backup uma vez por dia.
SAM_HEARTBEAT_MAX_AGE = {
    "expiration": env.int("SAM_EXPIRATION_MAX_AGE", default=15 * 60),
    "maintenance_reminders": env.int("SAM_REMINDERS_MAX_AGE", default=3 * 3600),
    "backup": env.int("SAM_BACKUP_MAX_AGE", default=26 * 3600),
}

# Monitor e alertas (BE-092, `manage.py monitor`). Canais: log `sam.alerts` (sempre),
# webhook (JSON com `text` e `content`: Slack, Discord, Teams/Google Chat via
# adaptador) e e-mail pelo SMTP acima. Detalhes em backend/docs/RUNBOOK.md.
SAM_MONITOR = {
    # Prontidão vista de dentro da rede do compose (a API responde em HTTP lá dentro).
    "READY_URL": env("SAM_MONITOR_READY_URL", default=""),
    # Diretório dos logs JSON do Nginx (access-AAAA-MM-DD.jsonl) para 5xx e latência.
    "ACCESS_LOG_DIR": env("SAM_MONITOR_ACCESS_LOG_DIR", default=""),
    "ACCESS_LOG_RETENTION_DAYS": env.int("SAM_ACCESS_LOG_RETENTION_DAYS", default=180),
    "WINDOW_SECONDS": env.int("SAM_MONITOR_WINDOW_SECONDS", default=300),
    "MIN_REQUESTS": env.int("SAM_MONITOR_MIN_REQUESTS", default=20),
    "ERROR_RATE": env.float("SAM_MONITOR_ERROR_RATE", default=0.05),
    "LATENCY_P95_SECONDS": env.float("SAM_MONITOR_LATENCY_P95_SECONDS", default=1.0),
    "DB_CONNECTIONS_RATIO": env.float("SAM_MONITOR_DB_CONNECTIONS_RATIO", default=0.8),
    "LOCK_WAIT_SECONDS": env.int("SAM_MONITOR_LOCK_WAIT_SECONDS", default=60),
    "DISK_PATHS": env.list("SAM_MONITOR_DISK_PATHS", default=[]),
    "DISK_FREE_RATIO": env.float("SAM_MONITOR_DISK_FREE_RATIO", default=0.10),
    # Falhas seguidas antes de alertar a indisponibilidade (verificação a cada 30 s:
    # 2 falhas = alerta em até ~70 s, dentro dos 2 min do critério de BE-092).
    "FAILURES_BEFORE_ALERT": env.int("SAM_MONITOR_FAILURES_BEFORE_ALERT", default=2),
    "REPEAT_SECONDS": env.int("SAM_ALERT_REPEAT_SECONDS", default=3600),
    "WEBHOOK_URL": env("SAM_ALERT_WEBHOOK_URL", default=""),
    "EMAILS": env.list("SAM_ALERT_EMAILS", default=[]),
    # "Dead man's switch" externo (ex.: healthchecks.io): GET a cada ciclo. Se o host
    # inteiro cair, o serviço externo deixa de receber o ping e alerta.
    "PING_URL": env("SAM_MONITOR_PING_URL", default=""),
    "ENVIRONMENT": env("SAM_ENVIRONMENT", default="produção"),
}

# OpenAPI
SPECTACULAR_SETTINGS = {
    "TITLE": "SAM — Simple Automotive Maintenance",
    "DESCRIPTION": (
        "API REST do SAM. Autenticação por cookie de sessão; métodos não "
        "seguros exigem o cabeçalho X-CSRFToken."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api",
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.openapi.drop_optional_response_fields",  # campos omitidos de propósito (BE-081)
    ],
}

# Logging
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_FORMAT = env("LOG_FORMAT", default="json")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": "apps.core.logging.RequestContextFilter"},
        "sensitive_data": {"()": "apps.core.logging.SensitiveDataFilter"},
    },
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "plain": {
            "format": (
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT if LOG_FORMAT in {"json", "plain"} else "json",
            "filters": ["request_context", "sensitive_data"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
