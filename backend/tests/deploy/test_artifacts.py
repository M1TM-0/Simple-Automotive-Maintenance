"""BE-088…BE-092 — Coerência entre os artefatos de implantação.

Os números que precisam combinar estão em arquivos diferentes (Dockerfile, Gunicorn,
compose, Nginx, settings); um ajuste num lado sem o outro quebra a produção sem
quebrar nenhum teste de unidade. A subida real com Docker é o deploy/smoke-test.sh
(job deploy-smoke do CI).
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml
from django.conf import settings
from django.core.management import call_command

REPO = Path(__file__).resolve().parents[3]
DOCKERFILE = (REPO / "backend" / "Dockerfile").read_text()
COMPOSE = yaml.safe_load((REPO / "deploy" / "compose.prod.yml").read_text())
NGINX = (REPO / "deploy" / "nginx" / "templates" / "sam.conf.template").read_text()
PROXY = (REPO / "deploy" / "nginx" / "snippets" / "proxy.conf").read_text()

pytestmark = pytest.mark.deploy


def stage(name):
    match = re.search(
        rf"^FROM .* AS {name}\n(.*?)(?=^FROM |\Z)", DOCKERFILE, re.M | re.S
    )
    assert match, f"estágio {name} ausente"
    return match.group(1)


def seconds(value):
    number, unit = re.fullmatch(r"(\d+)([smh]?)", str(value)).groups()
    return int(number) * {"": 1, "s": 1, "m": 60, "h": 3600}[unit]


def nginx_size(value):
    number, unit = re.fullmatch(r"(\d+)([km]?)", value).groups()
    return int(number) * {"": 1, "k": 1024, "m": 1024**2}[unit]


def gunicorn_conf():
    spec = importlib.util.spec_from_file_location(
        "conf", REPO / "backend" / "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ BE-088 imagem


def test_api_image_runs_as_unprivileged_user_with_healthcheck_and_gunicorn():
    api = stage("api")
    assert re.search(r"^USER sam:sam$", api, re.M)  # id -u = 10001, nunca 0
    assert "useradd --system --uid 10001" in stage("app")
    assert "HEALTHCHECK" in api and "/app/docker/healthcheck.py" in api
    # Forma exec: o Gunicorn é o PID 1 e recebe o SIGTERM do docker stop.
    assert (
        'CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "config.wsgi:application"]'
        in api
    )
    assert (
        DOCKERFILE.rstrip().split("\nFROM ")[-1].startswith("app AS api")
    )  # alvo padrão


def test_image_carries_init_sql_and_static_files_and_only_runtime_dependencies():
    app = stage("app")
    assert "COPY database/init.sql /app/database/init.sql" in app
    assert "SAM_INIT_SQL_PATH=/app/database/init.sql" in app
    assert "collectstatic --noinput" in app
    assert "requirements/base.txt" in stage("deps") and "dev.txt" not in stage("deps")


def test_secrets_and_local_files_stay_out_of_the_build_context():
    ignored = (REPO / ".dockerignore").read_text().split()
    for pattern in (
        "**/.env",
        "**/venv/",
        "deploy/secrets/",
        "deploy/certs/",
        "backend/media/",
        ".git/",
    ):
        assert pattern in ignored


def test_stop_grace_period_covers_the_gunicorn_graceful_timeout():
    conf = gunicorn_conf()
    assert (
        seconds(COMPOSE["services"]["api"]["stop_grace_period"])
        > conf.graceful_timeout + 5
    )


# ------------------------------------------------------------------ BE-089 proxy


def test_nginx_body_limit_lets_django_answer_its_own_413():
    limit = nginx_size(re.search(r"client_max_body_size (\w+);", NGINX).group(1))
    assert (
        limit > settings.SAM_MAX_UPLOAD_BYTES
    )  # o 413 em JSON do Django chega ao frontend
    assert "error_page 413 @too_large" in NGINX and '"detail"' in NGINX


def test_nginx_forwards_scheme_and_overwrites_the_client_ip():
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in PROXY
    assert (
        "proxy_set_header X-Forwarded-For $remote_addr;" in PROXY
    )  # nunca $proxy_add_…
    assert "proxy_set_header Host $host;" in PROXY
    env = COMPOSE["x-app-env"]
    assert env["USE_X_FORWARDED_PROTO"] == "True" and env["SAM_NUM_PROXIES"] == "1"


def test_nginx_timeouts_and_keepalive_fit_gunicorn():
    conf = gunicorn_conf()
    assert (
        seconds(re.search(r"proxy_read_timeout (\w+);", PROXY).group(1)) > conf.timeout
    )
    assert (
        seconds(re.search(r"keepalive_timeout (\w+);", NGINX).group(1)) < conf.keepalive
    )


def test_nginx_redirects_http_and_serves_the_same_origin():
    http_server = NGINX.split(
        "# ------------------------------------------------------------------ HTTPS"
    )[0]
    assert "return 301 https://${SAM_SERVER_NAME}$request_uri;" in http_server
    for location in (
        "location /api/",
        "location /admin/",
        "location /static/",
        "location / {",
    ):
        assert location in NGINX
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in NGINX
    assert "ssl_reject_handshake on;" in NGINX


def test_every_static_location_sends_the_security_headers():
    # add_header num location anula os herdados: cada um inclui o snippet.
    blocks = re.findall(r"location ([^{]+)\{(.*?)\n    \}", NGINX, re.S)
    static = [
        (name.strip(), body)
        for name, body in blocks
        if "alias" in body or "try_files" in body or "root" in body
    ]
    assert static
    for name, body in static:
        if "acme-challenge" in name:
            continue
        assert "security-headers.conf" in body, name


def test_production_frontend_config_is_installed_by_the_image():
    proxy = stage("proxy")
    assert (
        "COPY deploy/nginx/config.prod.js /usr/share/nginx/sam/frontend/js/config.js"
        in proxy
    )
    assert "COPY --from=app /app/staticfiles/" in proxy
    assert "NGINX_ENVSUBST_FILTER=^SAM_" in proxy


# ------------------------------------------------------------------ BE-091 compose


def test_compose_includes_the_expiration_job_and_keeps_the_database_private():
    services = COMPOSE["services"]
    assert set(services) == {"db", "api", "jobs", "monitor", "proxy", "backup"}
    assert (
        "run_expiration_jobs" in services["jobs"]["command"]
        and "--loop" in services["jobs"]["command"]
    )
    assert "ports" not in services["db"] and "ports" not in services["api"]
    assert services["proxy"]["ports"] == ["80:80", "443:443"]
    assert services["db"]["image"].startswith("postgres:16")


def test_only_the_api_owns_the_media_volume():
    """Regressão (BE-094): com o volume de mídia vazio o Docker copia para ele o dono do
    ponto de montagem da imagem a cada montagem. O proxy (root) deixava o volume root e
    todo upload dava 500. Só a API monta com cópia; os outros, só leitura e `nocopy`."""
    mounts = {}
    for name, service in COMPOSE["services"].items():
        for volume in service.get("volumes", []):
            if isinstance(volume, str) and volume.split(":")[0] == "media":
                mounts[name] = {"short": volume}
            elif isinstance(volume, dict) and volume.get("source") == "media":
                mounts[name] = volume
    assert mounts.pop("api") == {"short": "media:/app/media"}
    assert set(mounts) == {"proxy", "monitor", "backup"}
    for name, volume in mounts.items():
        assert volume.get("read_only") is True, name
        assert volume.get("volume", {}).get("nocopy") is True, name
    # E, por garantia, o ponto de montagem do proxy já nasce com o dono da API.
    assert "install -d -o 10001 -g 10001 -m 0755 /var/www/media" in stage("proxy")
    assert "install -d -o sam -g sam -m 0755 /app/media" in stage("app")


def test_backup_image_matches_the_database_major_version():
    backup = (REPO / "deploy" / "backup" / "Dockerfile").read_text()
    db_major = COMPOSE["services"]["db"]["image"].split(":")[1].split("-")[0]
    assert f"ARG POSTGRES_IMAGE=postgres:{db_major}-" in backup


def test_production_environment_is_fixed_in_the_compose():
    env = COMPOSE["x-app-env"]
    assert env["DJANGO_SETTINGS_MODULE"] == "config.settings.prod"
    assert env["CORS_ALLOWED_ORIGINS"] == ""  # mesma origem
    assert env["CSRF_TRUSTED_ORIGINS"] == "https://${SAM_SERVER_NAME}"


def test_production_env_example_documents_every_required_variable():
    example = (REPO / "deploy" / ".env.prod.example").read_text()
    for var in (
        "SAM_SERVER_NAME",
        "POSTGRES_PASSWORD",
        "SECRET_KEY",
        "EMAIL_HOST",
        "BACKUP_GPG_RECIPIENT_FILE",
        "SAM_ALERT_WEBHOOK_URL",
    ):
        assert re.search(rf"^#? ?{var}=", example, re.M), var
    assert not re.search(
        r"^(SECRET_KEY|POSTGRES_PASSWORD)=\S", example, re.M
    )  # sem segredo de exemplo


def test_deployment_files_are_git_ignored():
    ignored = (REPO / ".gitignore").read_text()
    for pattern in (
        "deploy/.env.prod",
        "deploy/certs/",
        "deploy/secrets/",
        "deploy/.deploy-state",
    ):
        assert pattern in ignored


# ------------------------------------------------------------------ BE-091 schema


@pytest.mark.django_db
def test_check_schema_confirms_the_init_sql_objects(capsys):
    call_command("check_schema", "--json")
    report = json.loads(capsys.readouterr().out)

    assert report["ok"] is True
    assert report["objects"]["tables"]["init_sql"] == 23
    assert report["objects"]["views"]["init_sql"] == 3
    assert report["objects"]["triggers"]["init_sql"] == 16
    assert report["objects"]["functions"]["init_sql"] == 26
    assert report["seeds"] == {"service": 62, "service_category": 11}
    assert report["pending_migrations"] == []


@pytest.mark.django_db
def test_check_schema_fails_when_an_object_is_missing(tmp_path, settings):
    from django.core.management.base import CommandError

    fake = tmp_path / "init.sql"
    fake.write_text(
        (REPO / "database" / "init.sql").read_text()
        + "\nCREATE TABLE TABELA_QUE_NAO_EXISTE (id INT);\n"
    )
    settings.SAM_INIT_SQL_PATH = fake

    with pytest.raises(CommandError, match="tabela_que_nao_existe"):
        call_command("check_schema")


# ------------------------------------------------------------------ BE-093 diagrama


@pytest.mark.django_db
def test_class_diagram_matches_the_migrated_schema():
    from apps.core.management.commands.schema_diagram import load_schema, render

    expected = render(load_schema())
    current = (REPO / "docs" / "DIAGRAMA_SAM.svg").read_text(encoding="utf-8")

    assert current == expected, (
        "docs/DIAGRAMA_SAM.svg desatualizado: rode `python manage.py schema_diagram` com o "
        "banco migrado e commite o SVG."
    )


def test_class_diagram_has_every_init_sql_table_and_status():
    svg = (REPO / "docs" / "DIAGRAMA_SAM.svg").read_text(encoding="utf-8")
    init_sql = (REPO / "database" / "init.sql").read_text()

    for table in re.findall(r"^CREATE TABLE (\w+)", init_sql, re.M):
        assert f'<g id="{table.lower()}">' in svg, table
    for status in ("waiting_approval", "under_review", "upheld", "refunded", "overdue"):
        assert status in svg
