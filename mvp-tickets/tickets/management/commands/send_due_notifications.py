from django.core.management.base import BaseCommand

from tickets.services import send_daily_expiring_ticket_summary


class Command(BaseCommand):
    help = "Envía un resumen diario de tickets por vencer a técnicos y administradores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--within",
            dest="within",
            type=int,
            default=24,
            help="Ventana de horas para considerar un ticket como próximo a vencer.",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Calcula el resumen sin enviar correos ni notificaciones.",
        )

    def handle(self, *args, **options):
        within = max(int(options["within"]), 1)
        dry_run = bool(options["dry_run"])

        summary = send_daily_expiring_ticket_summary(within_hours=within, dry_run=dry_run)
        message = (
            f"Tickets avisados: {summary.get('tickets', 0)} | "
            f"Destinatarios: {summary.get('recipients', 0)}"
        )
        if dry_run:
            message += " (dry-run)"
        self.stdout.write(self.style.SUCCESS(message))
