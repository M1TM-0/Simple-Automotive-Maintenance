"""BE-091/BE-092: batimento das rotinas, GET /api/health/jobs/ e healthcheck dos contêineres."""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest
from apps.core import heartbeat
from apps.core.models import JobHeartbeat
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, OperationalError, connection

BACKEND = Path(__file__).resolve().parents[3]


def _age(job, seconds):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE job_heartbeat SET date_last_success = clock_timestamp() - make_interval(secs => %s) "
            "WHERE job_name = %s",
            [seconds, job],
        )


# ------------------------------------------------------------------ batimento


@pytest.mark.django_db
def test_job_without_any_run_is_stale():
    status = heartbeat.job_status(heartbeat.EXPIRATION)

    assert status.age_seconds is None
    assert status.stale and not status.failing and not status.ok


@pytest.mark.django_db
def test_success_is_fresh_and_keeps_details():
    heartbeat.record_success(heartbeat.EXPIRATION, {"budgets_expired": 2})

    status = heartbeat.job_status(heartbeat.EXPIRATION)
    assert status.ok
    assert 0 <= status.age_seconds < 5
    assert JobHeartbeat.objects.get(pk="expiration").details == {"budgets_expired": 2}


@pytest.mark.django_db
def test_job_stopped_for_twenty_minutes_is_stale():
    heartbeat.record_success(heartbeat.EXPIRATION)
    _age(heartbeat.EXPIRATION, 20 * 60)

    status = heartbeat.job_status(heartbeat.EXPIRATION)
    assert status.stale and not status.ok
    assert status.max_age_seconds == 15 * 60


@pytest.mark.django_db
def test_failure_after_success_marks_the_job_as_failing_with_the_message():
    heartbeat.record_success(heartbeat.BACKUP)
    assert heartbeat.record_failure(heartbeat.BACKUP, RuntimeError("x" * 5000)) is True

    status = heartbeat.job_status(heartbeat.BACKUP)
    assert status.failing and not status.stale and not status.ok
    assert status.last_error == "x" * heartbeat.MAX_ERROR_LENGTH

    heartbeat.record_success(heartbeat.BACKUP)  # a próxima execução boa limpa a falha
    assert heartbeat.job_status(heartbeat.BACKUP).ok


@pytest.mark.django_db
def test_failure_without_database_is_not_raised():
    with mock.patch.object(
        heartbeat.transaction, "atomic", side_effect=OperationalError("down")
    ):
        assert (
            heartbeat.record_failure(heartbeat.EXPIRATION, OperationalError("down"))
            is False
        )


@pytest.mark.django_db
def test_job_name_is_validated_by_the_database():
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        heartbeat.record_success("Nome Inválido")


# ------------------------------------------------------------------ /api/health/jobs/


@pytest.mark.django_db
def test_health_jobs_follows_the_expiration_heartbeat(api_client):
    response = api_client.get("/api/health/jobs/")
    assert (response.status_code, response.json()) == (503, {"status": "stale"})

    heartbeat.record_success(heartbeat.EXPIRATION)
    response = api_client.get("/api/health/jobs/")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})

    heartbeat.record_failure(heartbeat.EXPIRATION, "deadlock")
    assert api_client.get("/api/health/jobs/").status_code == 503

    heartbeat.record_success(heartbeat.EXPIRATION)
    _age(heartbeat.EXPIRATION, 16 * 60)
    assert api_client.get("/api/health/jobs/").json() == {"status": "stale"}


@pytest.mark.django_db
def test_health_jobs_without_database_is_unavailable(api_client):
    with mock.patch.object(
        heartbeat, "job_status", side_effect=OperationalError("down")
    ):
        response = api_client.get("/api/health/jobs/")

    assert (response.status_code, response.json()) == (503, {"status": "unavailable"})


@pytest.mark.django_db
def test_health_jobs_does_not_leak_details(api_client):
    heartbeat.record_failure(heartbeat.EXPIRATION, "senha=segredo host=db")

    assert "segredo" not in api_client.get("/api/health/jobs/").content.decode()


# ------------------------------------------------------------------ rotina `jobs`


@pytest.mark.django_db
def test_expiration_job_records_heartbeat_and_touches_the_file(tmp_path):
    alive = tmp_path / "alive"

    call_command(
        "run_expiration_jobs", "--heartbeat-file", str(alive), stdout=StringIO()
    )

    assert heartbeat.job_status(heartbeat.EXPIRATION).ok
    assert set(JobHeartbeat.objects.get(pk="expiration").details) >= {
        "budgets_expired",
        "promotions_expired",
        "advertisements_activated",
    }
    assert time.time() - alive.stat().st_mtime < 5


# A rotina fecha a conexão depois da falha: precisa de teste transacional.
@pytest.mark.django_db(transaction=True)
def test_expiration_job_failure_is_recorded_and_the_file_is_not_touched(tmp_path):
    alive = tmp_path / "alive"
    with mock.patch(
        "apps.core.management.commands.run_expiration_jobs.run_once",
        side_effect=DatabaseError("deadlock detected"),
    ):
        with pytest.raises(CommandError):
            call_command("run_expiration_jobs", "--heartbeat-file", str(alive))

    status = heartbeat.job_status(heartbeat.EXPIRATION)
    assert status.failing and "deadlock detected" in status.last_error
    assert not alive.exists()


@pytest.mark.django_db
def test_reminders_record_their_own_heartbeat():
    call_command("send_maintenance_reminders", stdout=StringIO())
    assert heartbeat.job_status(heartbeat.REMINDERS).ok

    with mock.patch(
        "apps.vehicles.reminders.send_due_reminders", side_effect=DatabaseError("down")
    ):
        with pytest.raises(CommandError):
            call_command("send_maintenance_reminders")
    assert heartbeat.job_status(heartbeat.REMINDERS).failing


# A rotina fecha a conexão depois da falha: precisa de teste transacional.
@pytest.mark.django_db(transaction=True)
def test_loop_mode_sends_reminders_and_records_both_heartbeats():
    from apps.core.management.commands import run_expiration_jobs as module

    command = module.Command(stdout=StringIO())
    command.heartbeat_file = None
    command._execute(raise_on_error=False)
    command._send_reminders()

    assert heartbeat.job_status(heartbeat.EXPIRATION).ok
    assert heartbeat.job_status(heartbeat.REMINDERS).ok

    with mock.patch(
        "apps.vehicles.reminders.send_due_reminders", side_effect=DatabaseError("x")
    ):
        command._send_reminders()
    assert heartbeat.job_status(heartbeat.REMINDERS).failing


# ------------------------------------------------------------------ docker/healthcheck.py


def _load_healthcheck():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sam_healthcheck", BACKEND / "docker" / "healthcheck.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_api():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen["host"] = self.headers["Host"]
            seen["path"] = self.path
            self.send_response(503 if self.path.endswith("/ready/") else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], seen
    server.shutdown()


def test_healthcheck_uses_the_first_allowed_host(fake_api, monkeypatch):
    port, seen = fake_api
    monkeypatch.setenv("ALLOWED_HOSTS", ".sam.exemplo.com.br,www.sam.exemplo.com.br")
    check = _load_healthcheck()

    assert check.main(["--port", str(port)]) == 0
    assert seen == {"host": "sam.exemplo.com.br", "path": "/api/health/"}
    assert check.main(["/api/health/ready/", "--port", str(port)]) == 1


def test_healthcheck_fails_when_nothing_listens(monkeypatch):
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert _load_healthcheck().main(["--port", str(port), "--timeout", "1"]) == 1


def test_healthcheck_file_mode(tmp_path):
    check = _load_healthcheck()
    alive = tmp_path / "alive"

    assert check.main(["--file", str(alive)]) == 1  # ainda não rodou
    alive.touch()
    assert check.main(["--file", str(alive), "--max-age", "300"]) == 0
    old = time.time() - 400
    os.utime(alive, (old, old))
    assert check.main(["--file", str(alive), "--max-age", "300"]) == 1
