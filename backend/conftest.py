import pytest
from django.apps import apps
from django.db import connection
from rest_framework.test import APIClient

SEEDED_TABLES = {"service", "service_category"}


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture(autouse=True)
def clean_unmanaged_tables(request, django_db_blocker):
    """Tabelas managed=False não entram no flush de testes transacionais; limpa-as aqui."""
    yield

    marker = request.node.get_closest_marker("django_db")
    transactional = (marker and marker.kwargs.get("transaction")) or (
        "transactional_db" in request.fixturenames
    )
    if not transactional:
        return

    tables = sorted(
        model._meta.db_table
        for model in apps.get_models()
        if not model._meta.managed
        and model._meta.db_table not in SEEDED_TABLES
        and not model._meta.db_table.startswith("vw_")
    )
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"
        )  # sql-safe: nomes dos modelos


@pytest.fixture(autouse=True)
def clear_cache():
    """Limites de taxa e bloqueios de login vivem no cache: zera entre os testes."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


def open_account_session(account, role, client=None):
    """Abre uma sessão de cliente/oficina como o login faz (perfil, id e fingerprint)."""
    from apps.accounts.sessions import write_account_session

    client = client or APIClient()
    session = client.session
    write_account_session(session, account, role)
    session.save()
    client.cookies["sessionid"] = session.session_key
    return client


@pytest.fixture
def account_session():
    """Fábrica: `account_session(conta, "client"|"workshop")` → APIClient autenticado."""
    return open_account_session


@pytest.fixture
def client_account(db):
    from apps.core.tests.factories import ClientFactory

    return ClientFactory()


@pytest.fixture
def workshop_account(db):
    from apps.core.tests.factories import PagWorkshopFactory

    return PagWorkshopFactory().workshop


@pytest.fixture
def client_session(client_account):
    return open_account_session(client_account, "client")


@pytest.fixture
def workshop_session(workshop_account):
    return open_account_session(workshop_account, "workshop")


@pytest.fixture
def admin_session(db, django_user_model):
    user = django_user_model.objects.create_superuser(
        "admin", "admin@exemplo.com", "x" * 12
    )
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def ready_workshop(db):
    """Oficina com página e 1 serviço: cadastro concluído (BE-028) — libera `/workshop/*`."""
    from apps.core.tests.factories import PagWorkshopFactory, WorkshopServiceFactory

    workshop = PagWorkshopFactory().workshop
    WorkshopServiceFactory(workshop=workshop)
    return workshop


@pytest.fixture
def ready_workshop_session(ready_workshop):
    return open_account_session(ready_workshop, "workshop")
