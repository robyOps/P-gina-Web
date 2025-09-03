# tickets/management/commands/check_sla.py
from django.core.management.base import BaseCommand
from tickets.services import run_sla_check


class Command(BaseCommand):
    help = "Ejecuta el chequeo de SLA (warnings/breaches) y registra en AuditLog."

    def add_arguments(self, parser):
        # Compatibilidad: --warn-ratio y alias corto --warn
        parser.add_argument("--warn-ratio", dest="warn_ratio", type=float, default=0.8,
                            help="Porcentaje para warning (0.8 = 80%)")
        parser.add_argument("--warn", dest="warn_ratio", type=float,
                            help="Alias de --warn-ratio")

        # Compatibilidad: --dry-run y alias corto --dry
        parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="No envía correo ni escribe AuditLog")
        parser.add_argument("--dry", dest="dry_run", action="store_true",
                            help="Alias de --dry-run")

    def handle(self, *args, **opts):
        warn_ratio = float(opts["warn_ratio"])
        dry_run = bool(opts["dry_run"])

        # Unifica con el flujo de la UI (/reports/check-sla/)
        res = run_sla_check(warn_ratio=warn_ratio, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS(
            f"Warnings: {res.get('warnings', 0)}  |  Breaches: {res.get('breaches', 0)}"
        ))

