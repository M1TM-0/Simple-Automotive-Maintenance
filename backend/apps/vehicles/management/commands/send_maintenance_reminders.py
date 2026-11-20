"""BE-077: envia os lembretes de manutenção preventiva pendentes (idempotente).

Roda no serviço `jobs` do compose junto com `run_expiration_jobs`; pode rodar à
mão ou por cron. Duas execuções ao mesmo tempo não duplicam aviso (chave única
em MAINTENANCE_REMINDER).
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

logger = logging.getLogger("sam.jobs")


class Command(BaseCommand):
    help = "Avisa os clientes das manutenções preventivas próximas ou vencidas (uma vez por ciclo)."

    def handle(self, *args, **options):
        from apps.core import heartbeat
        from apps.vehicles.reminders import send_due_reminders

        try:
            sent = send_due_reminders()
            heartbeat.record_success(heartbeat.REMINDERS, {"reminders_sent": sent})
        except DatabaseError as exc:
            logger.error("Falha ao enviar lembretes de manutenção", exc_info=True)
            heartbeat.record_failure(heartbeat.REMINDERS, exc)
            raise CommandError(
                f"Falha ao enviar os lembretes de manutenção: {exc}"
            ) from exc
        logger.info("maintenance_reminders", extra={"reminders_sent": sent})
        self.stdout.write(f"lembretes de manutenção enviados: {sent}")
