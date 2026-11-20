"""Batimento das rotinas periódicas (BE-091/BE-092).

Cada rotina grava em `JOB_HEARTBEAT` quando termina: sucesso (com um resumo em
`details`) ou falha (com a mensagem). Quem lê é o monitor (`manage.py monitor`) e
`GET /api/health/jobs/`. Idades são calculadas pelo relógio do banco
(`clock_timestamp()`), o mesmo de quem grava: contêineres com relógios diferentes não
geram alarme falso.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import DatabaseError, connection, transaction

logger = logging.getLogger("sam.jobs")

EXPIRATION = "expiration"
REMINDERS = "maintenance_reminders"
BACKUP = "backup"

MAX_ERROR_LENGTH = 1000

RECORD_SUCCESS = """
INSERT INTO job_heartbeat (job_name, date_last_run, date_last_success, details)
VALUES (%s, clock_timestamp(), clock_timestamp(), %s::jsonb)
ON CONFLICT (job_name) DO UPDATE
SET date_last_run = EXCLUDED.date_last_run,
    date_last_success = EXCLUDED.date_last_success,
    details = EXCLUDED.details
"""

RECORD_FAILURE = """
INSERT INTO job_heartbeat (job_name, date_last_run, date_last_failure, last_error)
VALUES (%s, clock_timestamp(), clock_timestamp(), %s)
ON CONFLICT (job_name) DO UPDATE
SET date_last_run = EXCLUDED.date_last_run,
    date_last_failure = EXCLUDED.date_last_failure,
    last_error = EXCLUDED.last_error
"""

READ_STATUS = """
SELECT date_last_success,
       date_last_failure,
       last_error,
       EXTRACT(EPOCH FROM clock_timestamp() - date_last_success)
FROM job_heartbeat
WHERE job_name = %s
"""


def record_success(job, details=None):
    """Grava o sucesso na transação corrente (a rotina chama dentro da própria transação:
    o batimento só vale se o trabalho foi confirmado)."""
    with connection.cursor() as cursor:
        cursor.execute(RECORD_SUCCESS, [job, json.dumps(details or {}, default=str)])


def record_failure(job, error):
    """Grava a falha numa transação própria. Nunca levanta: com o banco fora do ar não há
    onde gravar, e o batimento parado já dispara o alerta. Devolve se gravou."""
    message = str(error).strip()[:MAX_ERROR_LENGTH] or error.__class__.__name__
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(RECORD_FAILURE, [job, message])
    except DatabaseError:
        logger.warning(
            "Não foi possível registrar a falha da rotina %s", job, exc_info=True
        )
        return False
    return True


@dataclass(frozen=True)
class JobStatus:
    job: str
    max_age_seconds: int
    last_success: datetime | None
    last_failure: datetime | None
    last_error: str | None
    age_seconds: float | None  # desde o último sucesso; None se nunca rodou com sucesso

    @property
    def stale(self):
        return self.age_seconds is None or self.age_seconds > self.max_age_seconds

    @property
    def failing(self):
        """A execução mais recente falhou (a falha é posterior ao último sucesso)."""
        if self.last_failure is None:
            return False
        return self.last_success is None or self.last_failure > self.last_success

    @property
    def ok(self):
        return not self.stale and not self.failing


def max_age(job):
    return settings.SAM_HEARTBEAT_MAX_AGE[job]


def job_status(job, max_age_seconds=None):
    """Situação da rotina pelo relógio do banco. Levanta DatabaseError se o banco cair."""
    limit = max_age(job) if max_age_seconds is None else max_age_seconds
    with connection.cursor() as cursor:
        cursor.execute(READ_STATUS, [job])
        row = cursor.fetchone()
    if row is None:
        return JobStatus(job, limit, None, None, None, None)
    success, failure, error, age = row
    return JobStatus(
        job, limit, success, failure, error, float(age) if age is not None else None
    )
