"""Monitor de produção (BE-092): `apps.core.monitoring`.

    python manage.py monitor --once [--json]     uma verificação; saída 1 se algo falhar
    python manage.py monitor --loop --interval 30 serviço `monitor` do compose (alerta)

`--once` não envia alertas (use para conferir à mão, no deploy ou no CI); `--loop`
alerta pelos canais de `SAM_MONITOR` e encerra no SIGTERM.
"""

import json
import logging
import signal
import threading
import time

from apps.core.monitoring import Monitor
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

logger = logging.getLogger("sam.monitor")


class Command(BaseCommand):
    help = "Verifica API, banco, rotinas, erros/latência e disco; alerta em --loop (BE-092)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument(
            "--once", action="store_true", help="Uma verificação, sem alertas."
        )
        mode.add_argument(
            "--loop", action="store_true", help="Verifica e alerta até SIGTERM."
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help="Segundos entre ciclos (padrão 30).",
        )
        parser.add_argument(
            "--json", action="store_true", help="Saída em JSON (--once)."
        )

    def handle(self, *args, **options):
        if options["once"]:
            return self._once(options["json"])
        if options["interval"] < 5:
            raise CommandError("--interval deve ser de pelo menos 5 segundos.")
        self._loop(options["interval"])

    def _once(self, as_json):
        results = Monitor().run_checks()
        failing = [r for r in results if not r.ok]
        if as_json:
            payload = [
                {"key": r.key, "ok": r.ok, "message": r.message} for r in results
            ]
            self.stdout.write(json.dumps(payload, ensure_ascii=False))
        else:
            for r in results:
                self.stdout.write(
                    f"{'OK   ' if r.ok else 'FALHA'} {r.key}: {r.message}"
                )
        if failing:
            raise CommandError(f"{len(failing)} verificação(ões) com falha.")

    def _loop(self, interval):
        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        monitor = Monitor()
        logger.info("Monitor iniciado", extra={"interval_seconds": interval})
        while not stop.is_set():
            started = time.monotonic()
            close_old_connections()  # como no fim de uma requisição: conexão velha ou quebrada sai
            try:
                results, alerts = monitor.cycle()
                failing = sum(1 for r in results if not r.ok)
                logger.info(
                    "monitor_cycle",
                    extra={
                        "checks": len(results),
                        "failing": failing,
                        "alerts": len(alerts),
                    },
                )
            except Exception:  # noqa: BLE001 — um ciclo com defeito não derruba o monitor
                logger.exception("Falha no ciclo do monitor")
            stop.wait(max(1.0, interval - (time.monotonic() - started)))
        logger.info("Monitor encerrado")
