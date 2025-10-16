import logging
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError

from tickets.models import Ticket
from tickets.services import bulk_recompute_ticket_label_suggestions


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Recalcula sugerencias de etiquetas para tickets seleccionados registrando métricas básicas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticket-id",
            type=int,
            action="append",
            dest="ticket_ids",
            help="Identificadores específicos de ticket a procesar (se puede repetir).",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            dest="threshold",
            help="Umbral mínimo de score (0-1). Si no se indica se usa el valor configurado.",
        )
        parser.add_argument(
            "--only-open",
            action="store_true",
            help="Limita el recalculo a tickets en estado OPEN o IN_PROGRESS.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Máximo de tickets a procesar (útil para ejecuciones parciales).",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=200,
            help="Cantidad de tickets a iterar por lote (por defecto 200).",
        )

    def _base_queryset(self, only_open: bool) -> Iterable[Ticket]:
        qs = Ticket.objects.all().select_related("priority", "area", "category")
        if only_open:
            qs = qs.filter(status__in=[Ticket.OPEN, Ticket.IN_PROGRESS])
        return qs.order_by("id")

    def handle(self, *args, **options):
        ticket_ids = options.get("ticket_ids") or []
        threshold = options.get("threshold")
        limit = options.get("limit")
        chunk_size = options.get("chunk_size") or 200

        if threshold is not None and not (0 <= threshold <= 1):
            raise CommandError("--threshold debe estar entre 0 y 1")

        if limit is not None and limit <= 0:
            raise CommandError("--limit debe ser mayor a cero")

        qs = self._base_queryset(options.get("only_open", False))

        if ticket_ids:
            qs = qs.filter(id__in=set(ticket_ids))

        if limit is not None:
            qs = qs[:limit]

        metrics = bulk_recompute_ticket_label_suggestions(
            queryset=qs,
            threshold=threshold,
            chunk_size=chunk_size,
        )

        logger.info(
            "Recomputo de sugerencias finalizado",
            extra={"metrics": metrics},
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Procesados {processed} tickets (detectados {detected}).".format(
                    processed=metrics.get("tickets_processed", 0),
                    detected=metrics.get("tickets_detected", 0),
                )
            )
        )
        self.stdout.write(
            "  - Sugerencias creadas: {created}".format(
                created=metrics.get("suggestions_created", 0)
            )
        )
        self.stdout.write(
            "  - Sugerencias actualizadas: {updated}".format(
                updated=metrics.get("suggestions_updated", 0)
            )
        )
        self.stdout.write(
            "  - Sugerencias eliminadas: {removed}".format(
                removed=metrics.get("suggestions_removed", 0)
            )
        )
        self.stdout.write(
            "  - Umbral aplicado: {threshold}".format(
                threshold=metrics.get("threshold")
            )
        )
        self.stdout.write(
            "  - Duración (s): {duration}".format(
                duration=metrics.get("duration_seconds")
            )
        )
