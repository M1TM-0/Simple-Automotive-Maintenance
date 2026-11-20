"""IP do cliente com e sem o proxy reverso (BE-089).

Defeito corrigido na Fase 7: sem `NUM_PROXIES` (None, o padrão do DRF) o IP passava a
ser o `X-Forwarded-For` enviado pelo próprio cliente — trocando o cabeçalho a cada
tentativa, qualquer um contornava os limites por IP (login, cadastro, redefinição).
Agora: `SAM_NUM_PROXIES=0` sem proxy (só REMOTE_ADDR) e `1` atrás do Nginx, que
reescreve o cabeçalho com `$remote_addr` (deploy/nginx/snippets/proxy.conf).
"""

import pytest
from apps.core.tests.factories import ClientFactory
from apps.core.throttles import RegisterRateThrottle, client_ip
from django.conf import settings as django_settings
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient, APIRequestFactory


def _request(**meta):
    return APIRequestFactory().post("/api/auth/register/", {}, format="json", **meta)


def test_without_proxy_forwarded_for_is_ignored():
    # Padrão (SAM_NUM_PROXIES=0): antes da Fase 7 era None e o DRF usava o cabeçalho.

    request = _request(REMOTE_ADDR="198.51.100.7", HTTP_X_FORWARDED_FOR="203.0.113.1")
    assert client_ip(request) == "198.51.100.7"  # cabeçalho forjado não muda o IP


def test_behind_nginx_the_client_ip_comes_from_forwarded_for(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}

    # O Nginx reescreve X-Forwarded-For com $remote_addr; o REMOTE_ADDR é o do proxy.
    request = _request(REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR="203.0.113.9")
    assert client_ip(request) == "203.0.113.9"
    # Mesmo se algo à frente anexar, vale o último (o que o nosso proxy escreveu).
    request = _request(
        REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.9"
    )
    assert client_ip(request) == "203.0.113.9"


def test_behind_nginx_each_client_has_its_own_rate_limit(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    throttle = RegisterRateThrottle()

    key_a = throttle.get_cache_key(
        _request(REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR="203.0.113.1"), None
    )
    key_b = throttle.get_cache_key(
        _request(REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR="203.0.113.2"), None
    )
    assert key_a != key_b  # sem NUM_PROXIES os dois cairiam no balde do IP do Nginx


def _login_from(api, ip=None, forwarded=None):
    meta = {"REMOTE_ADDR": ip or "198.51.100.7"}
    if forwarded:
        meta["HTTP_X_FORWARDED_FOR"] = forwarded
    return api.post(
        "/api/auth/login/",
        {"role": "client", "email": "ana@example.com", "password": "SenhaErrada000"},
        format="json",
        **meta,
    ).status_code


def test_default_settings_do_not_trust_forwarded_for():
    assert django_settings.REST_FRAMEWORK["NUM_PROXIES"] == 0


@pytest.mark.django_db
def test_forged_forwarded_for_does_not_bypass_the_login_limit():
    ClientFactory(email="ana@example.com", password_hash=make_password("SenhaTeste123"))
    api = APIClient()

    statuses = [_login_from(api, forwarded=f"203.0.113.{n}") for n in range(6)]

    assert statuses == [401] * 5 + [429]


@pytest.mark.django_db
def test_behind_nginx_one_client_does_not_lock_out_the_others(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    ClientFactory(email="ana@example.com", password_hash=make_password("SenhaTeste123"))
    api = APIClient()
    nginx = "172.18.0.5"

    attacker = [_login_from(api, nginx, "203.0.113.66") for _ in range(6)]
    other = _login_from(api, nginx, "203.0.113.10")

    assert attacker[-1] == 429
    assert other == 401  # outro cliente atrás do mesmo proxy ainda é atendido
