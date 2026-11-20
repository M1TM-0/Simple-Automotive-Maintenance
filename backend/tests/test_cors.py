"""BE-034: CORS com credenciais só para origens explícitas (P-15)."""

import pytest

ALLOWED = "http://localhost:5500"


@pytest.fixture(autouse=True)
def cors_settings(settings):
    settings.CORS_ALLOWED_ORIGINS = [ALLOWED]
    settings.CORS_ALLOW_ALL_ORIGINS = False


def test_allowed_origin_gets_exact_origin_and_credentials(client):
    response = client.get("/api/health/", HTTP_ORIGIN=ALLOWED)

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ALLOWED
    assert response["Access-Control-Allow-Credentials"] == "true"


def test_unlisted_origin_gets_no_cors_headers(client):
    response = client.get("/api/health/", HTTP_ORIGIN="http://evil.example")

    assert "Access-Control-Allow-Origin" not in response
    assert "Access-Control-Allow-Credentials" not in response


def test_preflight_allows_csrf_header(client):
    response = client.options(
        "/api/auth/login/",
        HTTP_ORIGIN=ALLOWED,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ALLOWED
    assert "x-csrftoken" in response["Access-Control-Allow-Headers"].lower()
