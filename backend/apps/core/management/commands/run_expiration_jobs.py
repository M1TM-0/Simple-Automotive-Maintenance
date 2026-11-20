import logging
import signal
import threading
import time
from pathlib import Path

from apps.core import heartbeat
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

logger = logging.getLogger("sam.jobs")

# Chave do pg_advisory_xact_lock: execuções da rotina não se sobrepõem (dois
# processos `jobs` não notificam o mesmo orçamento duas vezes).
JOB_LOCK_KEY = 0x5A3_0E4F

# Orçamentos que a rotina vai expirar e que o cliente já tinha recebido
# (atendimento em `waiting_approval`). Mesma condição de expire_pending_budgets();
# NOW() é o início da transação, igual para as duas consultas.
EXPIRING_SENT_BUDGETS = """
    SELECT b.id_budget
    FROM budget b
    JOIN attendance a ON a.id_attendance = b.id_attendance
    WHERE b.status_budget = 'pending'
      AND b.date_validity <= NOW()
      AND a.status_attendance = 'waiting_approval'
"""


def _notify_expired(candidate_ids):
    """BE-070: o cliente é avisado uma vez de cada orçamento que a rotina expirou."""
    from apps.attendances.models import Budget, BudgetStatus
    from apps.notifications import events

    expired = Budget.objects.filter(
        pk__in=candidate_ids, status_budget=BudgetStatus.EXPIRED
    ).select_related("attendance__workshop", "attendance__vehicle")
    for budget in expired:
        events.budget_expired(budget)
    return len(expired)


def _advertisement_jobs():
    """BE-076: põe no ar as divulgações pagas cujo período começou e marca o estorno
    das pagas que a expiração (ou outro caminho) cancelou. Roda depois das expirações,
    para não ativar divulgação de promoção que acabou de vencer."""
    from apps.promotions.services import (
        activate_due_advertisements,
        refund_cancelled_advertisements,
    )

    activated = activate_due_advertisements(skip_locked=True)
    refunded = refund_cancelled_advertisements(skip_locked=True)
    return activated, refunded


def run_once():
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [JOB_LOCK_KEY])
        cursor.execute(EXPIRING_SENT_BUDGETS)
        candidates = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT budgets_expired, promotions_expired, advertisements_completed "
            "FROM run_expiration_jobs()"
        )
        budgets, promotions, advertisements = cursor.fetchone()
        notified = _notify_expired(candidates) if candidates else 0
        activated, refunded = _advertisement_jobs()
        summary = {
            "budgets_expired": budgets,
            "promotions_expired": promotions,
            "advertisements_completed": advertisements,
            "budget_notifications": notified,
            "advertisements_activated": activated,
            "advertisements_refunded": refunded,
        }
        # BE-092: o batimento é confirmado junto com o trabalho (alerta se parar).
        heartbeat.record_success(heartbeat.EXPIRATION, summary)

    logger.info("expiration_jobs", extra=summary)
    return budgets, promotions, advertisements, activated, refunded


class Command(BaseCommand):
    help = (
        "Executa run_expiration_jobs() do banco (orçamentos, promoções e divulgações vencidos), "
        "ativa as divulgações pagas cujo período começou e marca os estornos (BE-076)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Repete a rotina continuamente até receber SIGTERM/SIGINT.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Segundos entre execuções no modo --loop (padrão: 60).",
        )
        parser.add_argument(
            "--reminders-interval",
            type=int,
            default=3600,
            help="No modo --loop, segundos entre envios dos lembretes de manutenção "
            "preventiva (BE-077; padrão: 3600; 0 desliga).",
        )
        parser.add_argument(
            "--heartbeat-file",
            help="Arquivo tocado a cada execução bem-sucedida (HEALTHCHECK do contêiner "
            "`jobs`: docker/healthcheck.py --file; BE-091).",
        )

    def handle(self, *args, **options):
        self.heartbeat_file = (
            Path(options["heartbeat_file"]) if options.get("heartbeat_file") else None
        )
        if not options["loop"]:
            self._execute(raise_on_error=True)
            return

        if options["interval"] < 1:
            raise CommandError("--interval deve ser maior que zero.")
        if options["reminders_interval"] < 0:
            raise CommandError("--reminders-interval não pode ser negativo.")

        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())

        next_reminders = time.monotonic()
        while not stop.is_set():
            self._execute(raise_on_error=False)
            if options["reminders_interval"] and time.monotonic() >= next_reminders:
                self._send_reminders()
                next_reminders = time.monotonic() + options["reminders_interval"]
            stop.wait(options["interval"])

    def _send_reminders(self):
        """BE-077: mesma rotina de `send_maintenance_reminders`, numa cadência própria."""
        from apps.vehicles.reminders import send_due_reminders

        try:
            sent = send_due_reminders()
            heartbeat.record_success(heartbeat.REMINDERS, {"reminders_sent": sent})
        except DatabaseError as exc:
            logger.error("Falha ao enviar lembretes de manutenção", exc_info=True)
            heartbeat.record_failure(heartbeat.REMINDERS, exc)
            connection.close()
            return
        logger.info("maintenance_reminders", extra={"reminders_sent": sent})
        self.stdout.write(f"lembretes de manutenção enviados: {sent}")

    def _execute(self, *, raise_on_error):
        try:
            budgets, promotions, advertisements, activated, refunded = run_once()
        except DatabaseError as exc:
            logger.error("Falha ao executar run_expiration_jobs()", exc_info=True)
            heartbeat.record_failure(heartbeat.EXPIRATION, exc)
            connection.close()
            if raise_on_error:
                raise CommandError(
                    f"Falha ao executar as rotinas de expiração: {exc}"
                ) from exc
            return

        if self.heartbeat_file is not None:
            self.heartbeat_file.touch()

        self.stdout.write(
            f"orçamentos expirados: {budgets} | promoções expiradas: {promotions} | "
            f"divulgações concluídas: {advertisements} | divulgações ativadas: {activated} | "
            f"estornos marcados: {refunded}"
        )
