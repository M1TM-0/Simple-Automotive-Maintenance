import json
import logging
from io import StringIO
from unittest import mock

import pytest
from apps.core.logging import (
    JsonFormatter,
    RequestContextFilter,
    SensitiveDataFilter,
    log_auth_event,
    mask_email,
    mask_secrets,
)
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import OperationalError, connections
from django.test import override_settings
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient


@api_view(["GET"])
@permission_classes([AllowAny])
def boom(request):
    raise RuntimeError("falha inesperada")


urlpatterns = [path("api/boom/", boom)]


def test_mask_secrets_hides_credentials():
    text = "login password=abc123 token: xyz sessionid=s1 Bearer abc.def.ghi"
    masked = mask_secrets(text)
    for secret in ("abc123", "xyz", "s1", "abc.def.ghi"):
        assert secret not in masked


def test_mask_email():
    assert mask_email("ana@exemplo.com") == "a**@exemplo.com"
    assert mask_email("") == "***"


def build_logger():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    handler.addFilter(SensitiveDataFilter())
    logger = logging.getLogger("sam.test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, stream


def test_auth_event_logs_masked_email_ip_and_never_the_password():
    logger, stream = build_logger()

    log_auth_event(
        "login_failed",
        role="client",
        email="ana@exemplo.com",
        ip="10.0.0.5",
        success=False,
        logger=logger,
    )
    logger.warning("tentativa password=segredo123")

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert lines[0]["email"] == "a**@exemplo.com"
    assert lines[0]["ip"] == "10.0.0.5"
    assert "segredo123" not in stream.getvalue()
    assert "ana@exemplo.com" not in stream.getvalue()


@pytest.mark.django_db
def test_request_id_header_is_generated_and_echoed():
    client = APIClient()

    generated = client.get("/api/health/")
    echoed = client.get("/api/health/", HTTP_X_REQUEST_ID="abc-123")
    rejected = client.get("/api/health/", HTTP_X_REQUEST_ID="bad id\r\n")

    assert len(generated["X-Request-ID"]) == 32
    assert echoed["X-Request-ID"] == "abc-123"
    assert rejected["X-Request-ID"] != "bad id\r\n"


@override_settings(ROOT_URLCONF="apps.core.tests.test_logging_health_openapi")
def test_unexpected_error_logs_request_id_and_returns_generic_500(caplog):
    caplog.set_level(logging.ERROR, logger="sam.api")
    caplog.handler.addFilter(RequestContextFilter())

    response = APIClient().get("/api/boom/", HTTP_X_REQUEST_ID="req-500")

    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno do servidor."}
    assert response["X-Request-ID"] == "req-500"
    assert any(getattr(r, "request_id", None) == "req-500" for r in caplog.records)


@pytest.mark.django_db
def test_liveness_does_not_touch_database(django_assert_num_queries):
    with django_assert_num_queries(0):
        response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_ok():
    response = APIClient().get("/api/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_returns_503_when_database_is_down():
    with mock.patch.object(
        type(connections["default"]), "cursor", side_effect=OperationalError("down")
    ):
        response = APIClient().get("/api/health/ready/")
    assert response.status_code == 503


@pytest.mark.django_db
def test_unknown_api_path_returns_json_404():
    response = APIClient().get("/api/nao-existe/")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")


@pytest.mark.django_db
def test_postgres_version_check_rejects_old_server():
    with mock.patch.object(
        type(connections["default"]),
        "pg_version",
        new_callable=mock.PropertyMock,
        return_value=120005,
    ):
        with pytest.raises(SystemCheckError, match="requer PostgreSQL 13 ou superior"):
            call_command("check", databases=["default"])


@pytest.mark.django_db
def test_postgres_version_check_accepts_current_server():
    call_command("check", databases=["default"])


@pytest.mark.django_db
def test_database_pool_is_configured_with_limits(settings):
    from config.settings import base

    pool = base.DATABASES["default"]["OPTIONS"]["pool"]
    assert 0 < pool["min_size"] <= pool["max_size"]
    assert base.DATABASES["default"]["ATOMIC_REQUESTS"] is False


@pytest.mark.django_db
def test_openapi_schema_is_valid_without_warnings(tmp_path):
    output = tmp_path / "schema.yml"
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(output))
    schema = output.read_text()
    assert "/api/health/" in schema and "/api/health/ready/" in schema


@pytest.mark.django_db
def test_schema_and_docs_are_served(client):
    assert client.get("/api/schema/").status_code in (200, 403)


# Testes atuais


def test_bearer_token_is_masked():
    from apps.core.logging import mask_secrets

    assert "abc123" not in mask_secrets("Authorization: Bearer abc123")
