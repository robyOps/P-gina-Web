import logging
import time

from django.core.management.base import BaseCommand, CommandError

from tickets.services import run_sla_check


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Evalúa alertas SLA registrando advertencias y brechas según corresponda."

    def add_arguments(self, parser):
        parser.add_argument(
            "--warn-ratio",
            type=float,
            default=0.8,
            help="Fracción del SLA a partir de la cual emitir advertencias (por defecto 0.8).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula la evaluación sin crear registros ni enviar notificaciones.",
        )

    def handle(self, *args, **options):
        warn_ratio = options.get("warn_ratio", 0.8)
        dry_run = options.get("dry_run", False)

        if warn_ratio <= 0 or warn_ratio > 1:
            raise CommandError("--warn-ratio debe estar en el rango (0, 1].")

        start = time.perf_counter()
        metrics = run_sla_check(warn_ratio=warn_ratio, dry_run=dry_run)
        duration = round(time.perf_counter() - start, 4)

        logger.info(
            "Evaluación de alertas ejecutada",
            extra={"metrics": {**metrics, "duration_seconds": duration, "dry_run": dry_run}},
        )

        label = "SIMULACIÓN" if dry_run else "EJECUCIÓN"
        self.stdout.write(self.style.SUCCESS(f"{label}: {metrics['warnings']} advertencias, {metrics['breaches']} brechas."))
        self.stdout.write(f"Duración (s): {duration}")
