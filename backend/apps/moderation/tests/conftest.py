import pytest
from rest_framework.test import APIClient


@pytest.fixture
def staff(django_user_model):
    """Moderador: `is_staff` sem ser superusuário (DP-03)."""
    return django_user_model.objects.create_user(
        "moderador", "mod@exemplo.com", "SenhaAdmin123", is_staff=True
    )


@pytest.fixture
def staff_client(staff):
    api = APIClient()
    api.force_login(staff)
    return api


@pytest.fixture
def commit(django_capture_on_commit_callbacks):
    """Executa os `on_commit` (notificações) dentro do teste não transacional."""

    def run(action, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return action(*args, **kwargs)

    return run
