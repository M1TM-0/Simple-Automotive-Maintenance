"""BE-092 — Monitor e alertas (apps/core/monitoring.py, `manage.py monitor`).

Critérios: "Dado o job parado por 20 minutos, então um alerta é emitido" e "Dado o
banco indisponível, então o alerta dispara em até 2 minutos".
"""

import json
import threading
import time
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

import pytest
from apps.core import heartbeat, monitoring
from apps.core.monitoring import (
    AccessLogReader,
    Alert,
    CheckResult,
    Monitor,
    Notifier,
    check_http,
    remove_old_access_logs,
)
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class Recorder:
    def __init__(self):
        self.sent = []

    def send(self, alert):
        self.sent.append(alert)


def config(**overrides):
    base = {
        **settings.SAM_MONITOR,
        "READY_URL": "",
        "ACCESS_LOG_DIR": "",
        "DISK_PATHS": [],
        "WEBHOOK_URL": "",
        "EMAILS": [],
        "PING_URL": "",
        "ENVIRONMENT": "teste",
    }
    return {**base, **overrides}


def make_monitor(clock=None, **overrides):
    clock = clock or Clock()
    recorder = Recorder()
    monitor = Monitor(config(**overrides), clock=clock, notifier=recorder)
    return monitor, recorder, clock


def _age(job, seconds):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE job_heartbeat SET date_last_success = clock_timestamp() - make_interval(secs => %s) WHERE job_name = %s",
            [seconds, job],
        )


def fresh_jobs():
    for job in (heartbeat.EXPIRATION, heartbeat.REMINDERS, heartbeat.BACKUP):
        heartbeat.record_success(job)


# ------------------------------------------------------------------ máquina de estados


def test_availability_alerts_only_after_consecutive_failures_then_repeats_and_resolves():
    monitor, _, clock = make_monitor(FAILURES_BEFORE_ALERT=2, REPEAT_SECONDS=3600)
    down = CheckResult("api", False, "API inacessível", availability=True)
    up = CheckResult("api", True, "API pronta", availability=True)

    assert monitor.evaluate([down]) == []  # um soluço não alerta
    clock.now += 30
    assert [a.state for a in monitor.evaluate([down])] == ["firing"]
    clock.now += 30
    assert monitor.evaluate([down]) == []  # não repete a cada ciclo
    clock.now += 3600
    assert [a.state for a in monitor.evaluate([down])] == ["repeat"]
    assert [a.state for a in monitor.evaluate([up])] == ["resolved"]
    assert monitor.evaluate([up]) == []


def test_ordinary_problem_alerts_at_once_and_events_never_resolve():
    monitor, _, _ = make_monitor()

    assert [
        a.state
        for a in monitor.evaluate([CheckResult("disk:/b", False, "pouco espaço")])
    ] == ["firing"]
    deadlock = CheckResult("db:deadlocks", False, "1 deadlock", event=True)
    assert [a.state for a in monitor.evaluate([deadlock])] == ["firing"]
    assert monitor.evaluate([CheckResult("db:deadlocks", True, "0", event=True)]) == []


def test_alert_text_names_the_environment():
    alert = Alert("firing", CheckResult("db", False, "Banco de dados indisponível"))
    assert (
        alert.text("produção") == "[SAM produção] ALERTA — Banco de dados indisponível"
    )


# ------------------------------------------------------------------ critérios de BE-092


@pytest.mark.django_db
def test_job_stopped_for_twenty_minutes_raises_an_alert():
    fresh_jobs()
    _age(heartbeat.EXPIRATION, 20 * 60)
    monitor, recorder, _ = make_monitor()

    monitor.cycle()

    alerts = [a for a in recorder.sent if a.result.key == "job:expiration"]
    assert [a.state for a in alerts] == ["firing"]
    assert (
        "sem execução bem-sucedida há 20 min (máximo 15 min)"
        in alerts[0].result.message
    )


# O monitor fecha a conexão quebrada para reconectar: teste transacional.
@pytest.mark.django_db(transaction=True)
def test_database_down_alerts_within_two_minutes():
    fresh_jobs()
    monitor, recorder, clock = make_monitor(FAILURES_BEFORE_ALERT=2)
    monitor.cycle()
    assert recorder.sent == []

    outage_started = clock.now
    with mock.patch.object(
        monitoring.connection,
        "cursor",
        side_effect=OperationalError("conexão recusada"),
    ):
        while not recorder.sent:
            clock.now += 30  # ciclo do serviço `monitor` (--interval 30)
            monitor.cycle()
            assert clock.now - outage_started <= 120, "o alerta não saiu em 2 minutos"

    assert [(a.state, a.result.key) for a in recorder.sent] == [("firing", "db")]
    assert "Banco de dados indisponível" in recorder.sent[0].result.message
    assert clock.now - outage_started == 60


# O monitor fecha a conexão quebrada para reconectar: teste transacional.
@pytest.mark.django_db(transaction=True)
def test_database_back_sends_resolved():
    fresh_jobs()
    monitor, recorder, clock = make_monitor(FAILURES_BEFORE_ALERT=1)
    with mock.patch.object(
        monitoring.connection, "cursor", side_effect=OperationalError("x")
    ):
        monitor.cycle()
    clock.now += 30
    monitor.cycle()

    assert [(a.state, a.result.key) for a in recorder.sent] == [
        ("firing", "db"),
        ("resolved", "db"),
    ]


# ------------------------------------------------------------------ rotinas


@pytest.mark.django_db
def test_failed_backup_is_alerted_with_its_error():
    fresh_jobs()
    heartbeat.record_failure(heartbeat.BACKUP, "pg_dump: conexão recusada")
    monitor, recorder, _ = make_monitor()

    monitor.cycle()

    [alert] = [a for a in recorder.sent if a.result.key == "job:backup"]
    assert (
        "Backup diário: a última execução falhou — pg_dump: conexão recusada"
        in alert.result.message
    )


@pytest.mark.django_db
def test_new_installation_gets_a_grace_period_for_jobs_that_never_ran():
    monitor, recorder, clock = make_monitor()

    monitor.cycle()
    assert not [a for a in recorder.sent if a.result.key.startswith("job:")]

    clock.now += 16 * 60  # a expiração (máximo 15 min) já devia ter rodado
    monitor.cycle()
    keys = [a.result.key for a in recorder.sent]
    assert "job:expiration" in keys and "job:backup" not in keys  # backup: 26 h


# ------------------------------------------------------------------ banco


@pytest.mark.django_db
def test_connection_usage_threshold():
    monitor, recorder, _ = make_monitor(DB_CONNECTIONS_RATIO=0.0)
    monitor.cycle()
    assert "db:connections" in [a.result.key for a in recorder.sent]


@pytest.mark.django_db
def test_new_deadlocks_are_reported_once():
    checks = monitoring.DatabaseChecks(config())
    with mock.patch.object(monitoring.connection, "cursor") as cursor:
        cursor.return_value.__enter__.return_value.fetchone.side_effect = [
            (5, 100, 3),
            (0, 0),  # 1º ciclo: só a linha de base
            (5, 100, 4),
            (0, 0),  # 2º: um deadlock novo
            (5, 100, 4),
            (0, 0),  # 3º: nada novo
        ]
        rounds = [{r.key: r for r in checks.run()}["db:deadlocks"] for _ in range(3)]

    assert [r.ok for r in rounds] == [True, False, True]
    assert rounds[1].details == {"new": 1, "total": 4}


@pytest.mark.django_db(transaction=True)
def test_session_waiting_on_a_lock_is_reported():
    import psycopg
    from apps.core.tests.factories import ClientFactory

    customer = ClientFactory()
    db = connection.settings_dict
    dsn = dict(
        host=db["HOST"] or "localhost",
        port=db["PORT"] or 5432,
        user=db["USER"],
        password=db["PASSWORD"],
        dbname=db["NAME"],
    )
    holder = psycopg.connect(**dsn)
    holder.execute(
        "SELECT 1 FROM client WHERE id_client = %s FOR UPDATE", [customer.pk]
    )
    waiter = psycopg.connect(**dsn, autocommit=True)
    thread = threading.Thread(
        target=lambda: waiter.execute(
            "UPDATE client SET name = 'x' WHERE id_client = %s", [customer.pk]
        ),
        daemon=True,
    )
    thread.start()
    try:
        time.sleep(1.5)
        results = {
            r.key: r
            for r in monitoring.DatabaseChecks(config(LOCK_WAIT_SECONDS=1)).run()
        }
    finally:
        holder.rollback()
        holder.close()
        thread.join(5)
        waiter.close()

    assert not results["db:locks"].ok
    assert results["db:locks"].details["waiting"] >= 1


# ------------------------------------------------------------------ HTTP (logs do Nginx)


def _line(when, uri="/api/chats/", status=200, request_time=0.02):
    return json.dumps(
        {
            "time": when.isoformat(),
            "uri": uri,
            "status": status,
            "request_time": request_time,
            "method": "GET",
        }
    )


def write_log(directory, lines, day=None):
    day = day or datetime.now(UTC).date()
    path = directory / f"access-{day.isoformat()}.jsonl"
    with path.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def test_error_rate_and_latency_from_the_nginx_logs(tmp_path):
    now = datetime.now(UTC)
    lines = [_line(now - timedelta(seconds=10)) for _ in range(25)]
    lines += [
        _line(now - timedelta(seconds=5), status=502, request_time=1.9)
        for _ in range(5)
    ]
    lines += [
        _line(now - timedelta(seconds=5), uri="/api/health/ready/", status=503)
        for _ in range(50)
    ]  # fora
    lines += [
        _line(now - timedelta(seconds=5), uri="/index.html", status=500)
        for _ in range(50)
    ]  # fora
    lines += [
        _line(now - timedelta(minutes=30), status=500) for _ in range(50)
    ]  # fora da janela
    write_log(tmp_path, lines)
    reader = AccessLogReader(tmp_path, 300)

    results = {r.key: r for r in check_http(reader, config(), now.timestamp())}

    assert not results["http:errors"].ok
    assert results["http:errors"].details == {"errors": 5, "total": 30}
    assert (
        not results["http:latency"].ok
        and results["http:latency"].details["p95_seconds"] > 1
    )


def test_log_reader_is_incremental_and_waits_for_complete_lines(tmp_path):
    now = datetime.now(UTC)
    path = write_log(tmp_path, [_line(now) for _ in range(3)])
    reader = AccessLogReader(tmp_path, 300)
    assert len(reader.collect(now.timestamp())) == 3

    with path.open("a") as fh:
        fh.write(_line(now) + "\n" + _line(now)[:20])  # uma linha inteira e um pedaço
    assert len(reader.collect(now.timestamp())) == 4
    with path.open("a") as fh:
        fh.write(_line(now)[20:] + "\n")
    assert len(reader.collect(now.timestamp())) == 5


def test_few_requests_do_not_alert(tmp_path):
    now = datetime.now(UTC)
    write_log(tmp_path, [_line(now, status=500) for _ in range(3)])

    results = check_http(AccessLogReader(tmp_path, 300), config(), now.timestamp())

    assert all(r.ok for r in results)


def test_access_logs_older_than_the_retention_are_removed(tmp_path):
    today = date(2026, 11, 18)
    for day in (date(2026, 5, 1), date(2026, 5, 22), date(2026, 11, 17)):
        (tmp_path / f"access-{day.isoformat()}.jsonl").write_text("{}\n")
    (tmp_path / "outro.log").write_text("x")

    removed = remove_old_access_logs(tmp_path, 180, today=today)

    assert removed == ["access-2026-05-01.jsonl"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "access-2026-05-22.jsonl",
        "access-2026-11-17.jsonl",
        "outro.log",
    ]


# ------------------------------------------------------------------ disco e /ready/


def test_low_disk_space_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        monitoring.shutil, "disk_usage", lambda path: mock.Mock(total=100, free=5)
    )

    [result] = monitoring.check_disks(config(DISK_PATHS=[str(tmp_path), "/nao/existe"]))

    assert not result.ok and "5%" in result.message


@pytest.fixture
def http_server():
    received = {"posts": [], "gets": [], "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            received["gets"].append((self.path, self.headers["Host"]))
            self.send_response(received["status"])
            self.end_headers()

        def do_POST(self):  # noqa: N802
            received["posts"].append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", received
    server.shutdown()


def test_ready_check_sends_the_production_host(http_server, settings):
    base, received = http_server
    settings.ALLOWED_HOSTS = ["sam.exemplo.com.br"]

    assert monitoring.check_ready(f"{base}/api/health/ready/").ok
    assert received["gets"] == [("/api/health/ready/", "sam.exemplo.com.br")]
    received["status"] = 503
    assert not monitoring.check_ready(f"{base}/api/health/ready/").ok


def test_unreachable_api_is_an_availability_problem():
    result = monitoring.check_ready("http://127.0.0.1:9/api/health/ready/", timeout=1)
    assert not result.ok and result.availability


@pytest.mark.django_db
def test_api_alert_is_suppressed_while_the_database_is_down(http_server):
    base, received = http_server
    received["status"] = 503
    monitor, recorder, _ = make_monitor(
        READY_URL=f"{base}/api/health/ready/", FAILURES_BEFORE_ALERT=1
    )

    with mock.patch.object(
        monitoring.connection, "cursor", side_effect=OperationalError("x")
    ):
        monitor.cycle()

    assert [a.result.key for a in recorder.sent] == ["db"]


# ------------------------------------------------------------------ canais


def test_notifier_sends_webhook_email_and_log(http_server, caplog):
    base, received = http_server
    notifier = Notifier(config(WEBHOOK_URL=f"{base}/hook", EMAILS=["ops@exemplo.com"]))

    with caplog.at_level("ERROR", logger="sam.alerts"):
        notifier.send(
            Alert("firing", CheckResult("db", False, "Banco de dados indisponível"))
        )

    [post] = received["posts"]
    assert (
        post["text"]
        == post["content"]
        == "[SAM teste] ALERTA — Banco de dados indisponível"
    )
    assert post["alert"] == {"key": "db", "state": "firing"}
    assert mail.outbox[0].subject == "[SAM teste] ALERTA — Banco de dados indisponível"
    assert mail.outbox[0].to == ["ops@exemplo.com"]
    assert any(getattr(r, "alert_key", None) == "db" for r in caplog.records)


def test_broken_channels_never_break_the_monitor(caplog):
    notifier = Notifier(
        config(WEBHOOK_URL="http://127.0.0.1:9/hook", EMAILS=["ops@exemplo.com"])
    )
    with mock.patch.object(
        monitoring, "send_mail", side_effect=ConnectionRefusedError("smtp")
    ):
        notifier.send(Alert("firing", CheckResult("db", False, "x")))

    assert "Falha ao enviar alerta pelo webhook" in caplog.text
    assert "Falha ao enviar alerta por e-mail" in caplog.text


@pytest.mark.django_db
def test_every_cycle_pings_the_external_dead_mans_switch(http_server):
    base, received = http_server
    fresh_jobs()
    monitor, _, _ = make_monitor(PING_URL=f"{base}/ping/abc")

    monitor.cycle()
    monitor.cycle()

    assert [path for path, _ in received["gets"]] == ["/ping/abc", "/ping/abc"]


# ------------------------------------------------------------------ comando


@pytest.mark.django_db
def test_monitor_once_reports_and_fails_when_something_is_wrong(settings):
    settings.SAM_MONITOR = config()
    fresh_jobs()
    out = StringIO()
    call_command("monitor", "--once", "--json", stdout=out)
    assert all(item["ok"] for item in json.loads(out.getvalue()))

    _age(heartbeat.EXPIRATION, 20 * 60)
    with pytest.raises(CommandError, match="1 verificação"):
        call_command("monitor", "--once", stdout=StringIO())


def test_monitor_requires_a_mode():
    with pytest.raises(CommandError):
        call_command("monitor")


@pytest.mark.django_db(transaction=True)
def test_loop_mode_alerts_and_stops_on_sigterm(tmp_path):
    """O serviço `monitor` de verdade: processo próprio, alerta no log e sai no SIGTERM."""
    import os
    import signal
    import subprocess
    import sys

    heartbeat.record_success(heartbeat.EXPIRATION)
    _age(heartbeat.EXPIRATION, 20 * 60)
    db = connection.settings_dict
    url = f"postgres://{db['USER']}:{db['PASSWORD']}@{db['HOST'] or 'localhost'}:{db['PORT'] or 5432}/{db['NAME']}"
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.test",
        "TEST_DATABASE_URL": url,
        "LOG_FORMAT": "json",
    }
    env.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
    proc = subprocess.Popen(
        [sys.executable, "manage.py", "monitor", "--loop", "--interval", "5"],
        cwd=settings.BASE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines, first_cycle = [], threading.Event()

    def read():
        for line in proc.stdout:
            lines.append(line)
            if "monitor_cycle" in line:
                first_cycle.set()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        # Folga para máquina carregada (suíte inteira com cobertura).
        first_cycle.wait(90)
        proc.send_signal(signal.SIGTERM)
        proc.wait(30)
    finally:
        if proc.poll() is None:
            proc.kill()
        reader.join(10)
    out = "".join(lines)

    assert first_cycle.is_set(), out
    assert proc.returncode == 0, out
    assert "Rotina de expiração" in out and "ALERTA" in out, out
    assert "Monitor encerrado" in out, out
