"""Monitor e alertas do SAM (BE-092; seção 13.5 do backlog).

Roda no serviço `monitor` do compose (`manage.py monitor --loop --interval 30`) e
verifica, a cada ciclo:

* **api** — `GET /api/health/ready/` dentro da rede do compose (API + banco + schema);
* **db** — o banco responde; **db:connections** (uso de `max_connections`),
  **db:deadlocks** (novos deadlocks em `pg_stat_database`), **db:locks** (sessões
  esperando lock há mais de N segundos);
* **job:<rotina>** — batimento da expiração (15 min), dos lembretes (3 h) e do backup
  (26 h), ou última execução com falha (`apps.core.heartbeat`);
* **http:errors** / **http:latency** — taxa de 5xx e p95 da latência das rotas `/api/`
  nos últimos 5 min, pelos logs JSON do Nginx;
* **disk:<caminho>** — espaço livre dos volumes (mídia, backups, logs).

Alertas: um por problema quando ele aparece (indisponibilidade só depois de
`FAILURES_BEFORE_ALERT` falhas seguidas, para não alarmar por um soluço), repetido a
cada `REPEAT_SECONDS` enquanto durar e "resolvido" quando volta. Canais: log
`sam.alerts` (sempre), webhook e e-mail (`settings.SAM_MONITOR`). Banco fora do ar →
alerta em até ~80 s (2 ciclos de 30 s + espera do pool), dentro dos 2 min de BE-092.
"""

import json
import logging
import os
import shutil
import statistics
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.db import DatabaseError, connection

from . import heartbeat

logger = logging.getLogger("sam.alerts")

JOB_LABELS = {
    heartbeat.EXPIRATION: "Rotina de expiração (orçamentos, promoções, divulgações)",
    heartbeat.REMINDERS: "Lembretes de manutenção preventiva",
    heartbeat.BACKUP: "Backup diário",
}


@dataclass
class CheckResult:
    key: str
    ok: bool
    message: str
    availability: bool = False  # espera FAILURES_BEFORE_ALERT falhas seguidas
    event: bool = False  # acontecimento pontual (deadlock): sem aviso de "resolvido"
    details: dict = field(default_factory=dict)


@dataclass
class Alert:
    state: str  # firing | repeat | resolved
    result: CheckResult

    def text(self, environment):
        label = {
            "firing": "ALERTA",
            "repeat": "AINDA EM ALERTA",
            "resolved": "RESOLVIDO",
        }[self.state]
        return f"[SAM {environment}] {label} — {self.result.message}"


def _duration(seconds):
    if seconds is None:
        return "nunca"
    minutes = int(seconds // 60)
    if minutes < 120:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def _first_allowed_host():
    hosts = [h for h in settings.ALLOWED_HOSTS if h and h != "*"]
    return hosts[0].lstrip(".") if hosts else "localhost"


# ------------------------------------------------------------------ verificações


def check_ready(url, timeout=5.0):
    request = urllib.request.Request(
        url, headers={"Host": _first_allowed_host(), "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except OSError as exc:
        return CheckResult(
            "api",
            False,
            f"API inacessível ({exc.__class__.__name__}: {exc})",
            availability=True,
        )
    if status != 200:
        return CheckResult(
            "api",
            False,
            f"API não está pronta: /api/health/ready/ respondeu {status}",
            availability=True,
        )
    return CheckResult("api", True, "API pronta", availability=True)


class DatabaseChecks:
    def __init__(self, config):
        self.config = config
        self.last_deadlocks = None

    def run(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.execute(
                    "SELECT (SELECT count(*) FROM pg_stat_activity), current_setting('max_connections')::int, "
                    "(SELECT deadlocks FROM pg_stat_database WHERE datname = current_database())"
                )
                used, maximum, deadlocks = cursor.fetchone()
                cursor.execute(
                    "SELECT count(*), COALESCE(max(EXTRACT(EPOCH FROM clock_timestamp() - query_start)), 0) "
                    "FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                    "AND clock_timestamp() - query_start > make_interval(secs => %s)",
                    [self.config["LOCK_WAIT_SECONDS"]],
                )
                waiting, longest = cursor.fetchone()
        except DatabaseError as exc:
            connection.close()  # o próximo ciclo reconecta
            return [
                CheckResult(
                    "db",
                    False,
                    f"Banco de dados indisponível ({str(exc).strip()[:200]})",
                    availability=True,
                )
            ]

        results = [
            CheckResult("db", True, "Banco de dados respondendo", availability=True)
        ]

        ratio = used / maximum if maximum else 0
        results.append(
            CheckResult(
                "db:connections",
                ratio <= self.config["DB_CONNECTIONS_RATIO"],
                f"Conexões do banco em {used}/{maximum} ({ratio:.0%}; limite {self.config['DB_CONNECTIONS_RATIO']:.0%})",
                details={"used": used, "max": maximum},
            )
        )

        new = (
            0
            if self.last_deadlocks is None
            else max(0, deadlocks - self.last_deadlocks)
        )
        self.last_deadlocks = deadlocks
        results.append(
            CheckResult(
                "db:deadlocks",
                new == 0,
                f"{new} deadlock(s) novo(s) no banco desde a última verificação (total {deadlocks})",
                event=True,
                details={"new": new, "total": deadlocks},
            )
        )

        results.append(
            CheckResult(
                "db:locks",
                waiting == 0,
                f"{waiting} sessão(ões) esperando lock há mais de {self.config['LOCK_WAIT_SECONDS']} s "
                f"(a mais antiga há {float(longest):.0f} s)",
                details={"waiting": waiting, "longest_seconds": float(longest)},
            )
        )
        return results


def check_jobs(started_at, now):
    results = []
    for job, label in JOB_LABELS.items():
        try:
            status = heartbeat.job_status(job)
        except DatabaseError:
            connection.close()
            return []  # o alerta do banco já cobre
        # Instalação nova: a rotina ainda não teve tempo de rodar a primeira vez.
        if (
            status.age_seconds is None
            and status.last_failure is None
            and now - started_at < status.max_age_seconds
        ):
            continue
        limit = _duration(status.max_age_seconds)
        if status.failing:
            message = f"{label}: a última execução falhou — {(status.last_error or '').strip()[:300]}"
        elif status.stale:
            message = f"{label}: sem execução bem-sucedida há {_duration(status.age_seconds)} (máximo {limit})"
        else:
            message = f"{label}: em dia (última há {_duration(status.age_seconds)})"
        results.append(
            CheckResult(
                f"job:{job}",
                status.ok,
                message,
                details={"age_seconds": status.age_seconds},
            )
        )
    return results


class AccessLogReader:
    """Lê incrementalmente os logs JSON do Nginx (access-AAAA-MM-DD.jsonl) e mantém as
    requisições `/api/` (fora `/api/health/`) dos últimos `window` segundos."""

    START_TAIL_BYTES = 5 * 1024 * 1024

    def __init__(self, directory, window):
        self.directory = Path(directory)
        self.window = window
        self.offsets = {}
        self.entries = deque()  # (epoch, status, request_time)

    def _files(self, today):
        for day in (today - timedelta(days=1), today):
            path = self.directory / f"access-{day.isoformat()}.jsonl"
            if path.exists():
                yield path

    def _read(self, path):
        size = path.stat().st_size
        offset = self.offsets.get(path)
        partial = False
        if offset is None:  # primeira leitura: só o fim do arquivo
            offset = max(0, size - self.START_TAIL_BYTES)
            partial = offset > 0
        if offset > size:  # arquivo truncado/recriado
            offset = 0
        with path.open("rb") as fh:
            fh.seek(offset)
            data = fh.read()
        end = data.rfind(b"\n") + 1  # linha incompleta fica para o próximo ciclo
        self.offsets[path] = offset + end
        lines = data[:end].splitlines()
        if partial and lines:
            lines = lines[1:]
        for raw in lines:
            try:
                item = json.loads(raw)
                uri = item["uri"]
                if not uri.startswith("/api/") or uri.startswith("/api/health/"):
                    continue
                stamp = datetime.fromisoformat(item["time"]).timestamp()
                self.entries.append(
                    (stamp, int(item["status"]), float(item["request_time"]))
                )
            except (ValueError, KeyError, TypeError):
                continue

    def collect(self, now):
        if not self.directory.is_dir():
            return None
        today = datetime.fromtimestamp(now).date()
        for path in self._files(today):
            self._read(path)
        for path in [p for p in self.offsets if not p.exists()]:
            del self.offsets[path]
        cutoff = now - self.window
        recent = sorted((e for e in self.entries if e[0] >= cutoff), key=lambda e: e[0])
        self.entries = deque(recent)
        return recent


def check_http(reader, config, now):
    entries = reader.collect(now)
    if entries is None:
        return []
    total = len(entries)
    errors = sum(1 for _, status, _ in entries if status >= 500)
    window = _duration(config["WINDOW_SECONDS"])
    if total < config["MIN_REQUESTS"]:
        return [
            CheckResult(
                "http:errors",
                True,
                f"Poucas requisições na janela de {window} ({total})",
            ),
            CheckResult(
                "http:latency",
                True,
                f"Poucas requisições na janela de {window} ({total})",
            ),
        ]
    ratio = errors / total
    times = [t for _, _, t in entries]
    p95 = (
        statistics.quantiles(times, n=20, method="inclusive")[18]
        if len(times) > 1
        else times[0]
    )
    return [
        CheckResult(
            "http:errors",
            ratio <= config["ERROR_RATE"],
            f"{ratio:.1%} das requisições da API com erro 5xx em {window} ({errors}/{total}; limite {config['ERROR_RATE']:.0%})",
            details={"errors": errors, "total": total},
        ),
        CheckResult(
            "http:latency",
            p95 <= config["LATENCY_P95_SECONDS"],
            f"Latência p95 da API em {p95 * 1000:.0f} ms nos últimos {window} (limite {config['LATENCY_P95_SECONDS'] * 1000:.0f} ms; {total} requisições)",
            details={"p95_seconds": p95, "total": total},
        ),
    ]


def check_disks(config):
    results = []
    for path in config["DISK_PATHS"]:
        if not os.path.exists(path):
            continue
        usage = shutil.disk_usage(path)
        free = usage.free / usage.total if usage.total else 1
        results.append(
            CheckResult(
                f"disk:{path}",
                free >= config["DISK_FREE_RATIO"],
                f"Espaço livre em {path}: {free:.0%} ({usage.free // 2**20} MB; mínimo {config['DISK_FREE_RATIO']:.0%})",
                details={"free_ratio": free},
            )
        )
    return results


def remove_old_access_logs(directory, retention_days, today=None):
    """Apaga access-AAAA-MM-DD.jsonl mais velhos que a retenção (Marco Civil: 6 meses)."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    limit = (today or date.today()) - timedelta(days=retention_days)
    removed = []
    for path in directory.glob("access-*.jsonl"):
        try:
            day = date.fromisoformat(path.stem.removeprefix("access-"))
        except ValueError:
            continue
        if day < limit:
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


# ------------------------------------------------------------------ alertas


class Notifier:
    def __init__(self, config):
        self.config = config

    def send(self, alert):
        text = alert.text(self.config["ENVIRONMENT"])
        level = logging.INFO if alert.state == "resolved" else logging.ERROR
        logger.log(
            level,
            text,
            extra={
                "alert_key": alert.result.key,
                "alert_state": alert.state,
                "alert_details": alert.result.details,
            },
        )
        if self.config["WEBHOOK_URL"]:
            self._webhook(text, alert)
        if self.config["EMAILS"]:
            self._email(text)

    def _webhook(self, text, alert):
        body = json.dumps(
            {
                "text": text,
                "content": text,
                "alert": {"key": alert.result.key, "state": alert.state},
            },
            ensure_ascii=False,
        ).encode()
        request = urllib.request.Request(
            self.config["WEBHOOK_URL"],
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except OSError:
            logger.warning("Falha ao enviar alerta pelo webhook", exc_info=True)

    def _email(self, text):
        try:
            send_mail(text[:180], text, None, self.config["EMAILS"])
        except Exception:  # noqa: BLE001 — o alerta por e-mail nunca derruba o monitor
            logger.warning("Falha ao enviar alerta por e-mail", exc_info=True)


class Monitor:
    def __init__(self, config=None, clock=time.time, notifier=None):
        self.config = config or settings.SAM_MONITOR
        self.clock = clock
        self.started_at = clock()
        self.notifier = notifier or Notifier(self.config)
        self.database = DatabaseChecks(self.config)
        self.reader = (
            AccessLogReader(
                self.config["ACCESS_LOG_DIR"], self.config["WINDOW_SECONDS"]
            )
            if self.config["ACCESS_LOG_DIR"]
            else None
        )
        self.state = {}
        self.last_cleanup = 0.0

    def run_checks(self):
        now = self.clock()
        results = self.database.run()
        db_ok = results[0].ok
        if self.config["READY_URL"]:
            ready = check_ready(self.config["READY_URL"])
            # Banco fora do ar derruba o /ready/ também: um alerta só (o do banco).
            if db_ok or ready.ok:
                results.append(ready)
        if db_ok:
            results.extend(check_jobs(self.started_at, now))
        if self.reader is not None:
            results.extend(check_http(self.reader, self.config, now))
        results.extend(check_disks(self.config))
        return results

    def evaluate(self, results):
        now = self.clock()
        alerts = []
        for result in results:
            state = self.state.setdefault(
                result.key, {"failures": 0, "alerted_at": None}
            )
            if result.ok:
                if state["alerted_at"] is not None and not result.event:
                    alerts.append(Alert("resolved", result))
                state.update(failures=0, alerted_at=None)
                continue
            state["failures"] += 1
            needed = self.config["FAILURES_BEFORE_ALERT"] if result.availability else 1
            if state["failures"] < needed:
                continue
            if state["alerted_at"] is None:
                alerts.append(Alert("firing", result))
                state["alerted_at"] = now
            elif now - state["alerted_at"] >= self.config["REPEAT_SECONDS"]:
                alerts.append(Alert("repeat", result))
                state["alerted_at"] = now
        return alerts

    def cycle(self):
        results = self.run_checks()
        alerts = self.evaluate(results)
        for alert in alerts:
            self.notifier.send(alert)
        self._ping()
        self._cleanup()
        return results, alerts

    def _ping(self):
        url = self.config["PING_URL"]
        if not url:
            return
        try:
            with urllib.request.urlopen(url, timeout=10):
                pass
        except OSError:
            logger.warning("Falha no ping do monitor externo (%s)", url)

    def _cleanup(self):
        now = self.clock()
        if not self.config["ACCESS_LOG_DIR"] or now - self.last_cleanup < 3600:
            return
        self.last_cleanup = now
        removed = remove_old_access_logs(
            self.config["ACCESS_LOG_DIR"], self.config["ACCESS_LOG_RETENTION_DAYS"]
        )
        if removed:
            logging.getLogger("sam.monitor").info(
                "Logs de acesso removidos pela retenção", extra={"files": removed}
            )
