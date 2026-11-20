from .base import *

SECRET_KEY = "test-only-secret-key"

DEBUG = False

ALLOWED_HOSTS = ["testserver"]

DATABASES = {
    "default": env.db_url_config(
        env(
            "TEST_DATABASE_URL",
            default=DATABASE_URL or "postgres://sam:sam@localhost:5432/sam",
        )
    ),
}

DATABASES["default"]["ATOMIC_REQUESTS"] = False

LOG_LEVEL = "WARNING"

# Testes nunca consultam a Overpass pública (BE-094): quem testa a integração liga uma URL
# falsa com `settings.SAM_OVERPASS = {...}` e simula a resposta.
SAM_OVERPASS = {**SAM_OVERPASS, "URL": ""}
