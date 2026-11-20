"""BE-035: administração por usuário Django `is_staff` (DP-03) e log de auditoria,
provados pelas rotas reais de BE-073/BE-074."""

import logging
import uuid

import pytest
from apps.core.tests.factories import AttendanceFactory, deliver_attendance, make_review
from apps.moderation.permissions import ADMIN_PERMISSIONS, IsAdmin
from apps.moderation.views import AdminViewMixin
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

URL = "/api/admin/denunciations/"
pytestmark = pytest.mark.django_db


def _admin_api_views():
    """(rota, classe da view) de tudo que está montado sob `api/admin/`."""

    def walk(patterns, prefix):
        for entry in patterns:
            route = prefix + str(entry.pattern)
            if isinstance(entry, URLResolver):
                yield from walk(entry.url_patterns, route)
            elif isinstance(entry, URLPattern) and route.startswith("api/admin/"):
                yield route, getattr(entry.callback, "view_class", None)

    return list(walk(get_resolver().url_patterns, ""))


def test_base_mixin_uses_admin_permission():
    assert AdminViewMixin.permission_classes == ADMIN_PERMISSIONS == [IsAdmin]


def test_every_admin_route_uses_the_admin_mixin():
    routes = _admin_api_views()

    assert len(routes) == 6
    for route, view in routes:
        assert view is not None and issubclass(view, AdminViewMixin), route
        assert view.permission_classes == ADMIN_PERMISSIONS, route


def test_visitor_gets_401(api_client):
    response = api_client.get(URL)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"


def test_client_gets_403(client_session):
    response = client_session.get(URL)

    assert response.status_code == 403
    assert response.json() == {"detail": "Esta ação é exclusiva para administradores."}


def test_workshop_gets_403(workshop_session):
    assert workshop_session.get(URL).status_code == 403
    assert (
        workshop_session.post(f"/api/admin/reviews/{uuid.uuid4()}/hide/").status_code
        == 403
    )


def test_non_staff_django_user_gets_401(django_user_model):
    api = APIClient()
    api.force_login(
        django_user_model.objects.create_user("comum", "c@exemplo.com", "x" * 12)
    )

    assert api.get(URL).status_code == 401


def test_staff_reads_the_list(staff_client):
    response = staff_client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }


def test_admin_write_is_audited(staff_client, staff, caplog):
    budget, *_ = deliver_attendance(AttendanceFactory())
    review = make_review(budget)
    url = f"/api/admin/reviews/{review.pk}/hide/"

    with caplog.at_level(logging.INFO, logger="sam.audit"):
        assert staff_client.post(url).status_code == 200

    records = [r for r in caplog.records if r.name == "sam.audit"]
    assert len(records) == 1
    record = records[0]
    assert record.getMessage() == "admin.review.hide"
    assert (record.admin_id, record.method, record.path, record.status) == (
        staff.pk,
        "POST",
        url,
        200,
    )
    assert (record.target_type, record.target_id) == ("review", str(review.pk))


def test_failed_admin_write_is_audited_too(staff_client, caplog):
    with caplog.at_level(logging.INFO, logger="sam.audit"):
        assert (
            staff_client.post(f"/api/admin/reviews/{uuid.uuid4()}/hide/").status_code
            == 404
        )

    [record] = [r for r in caplog.records if r.name == "sam.audit"]
    assert record.status == 404


def test_admin_read_is_not_audited(staff_client, caplog):
    with caplog.at_level(logging.INFO, logger="sam.audit"):
        staff_client.get(URL)

    assert not [r for r in caplog.records if r.name == "sam.audit"]


def test_admin_write_requires_csrf(staff):
    api = APIClient(enforce_csrf_checks=True)
    api.force_login(staff)

    response = api.post(f"/api/admin/reviews/{uuid.uuid4()}/hide/")

    assert response.status_code == 403


def test_django_admin_login_and_failure_are_audited(staff, caplog):
    browser = APIClient()
    with caplog.at_level(logging.INFO, logger="sam.audit"):
        browser.post("/admin/login/", {"username": "moderador", "password": "errada"})
        browser.post(
            "/admin/login/", {"username": "moderador", "password": "SenhaAdmin123"}
        )

    messages = [r.getMessage() for r in caplog.records if r.name == "sam.audit"]
    assert "admin.login_failed" in messages
    assert "admin.login" in messages
    assert all("SenhaAdmin123" not in str(r.__dict__) for r in caplog.records)
