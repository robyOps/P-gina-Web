import logging
import time

from django.core.management.base import BaseCommand, CommandError

from tickets.clustering import train_ticket_clusters


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reentrena los clústeres de tickets usando similitud textual."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clusters",
            type=int,
            default=5,
            help="Cantidad de clústeres a generar (entero positivo).",
        )

    def handle(self, *args, **options):
        clusters = options["clusters"]
        if clusters <= 0:
            raise CommandError("--clusters debe ser un entero mayor a cero")

        start = time.perf_counter()
        summary = train_ticket_clusters(num_clusters=clusters)
        duration = round(time.perf_counter() - start, 4)

        if summary.total_tickets == 0:
            logger.info(
                "Clusterización ejecutada sin tickets",
                extra={
                    "requested_clusters": clusters,
                    "duration_seconds": duration,
                },
            )
            self.stdout.write(self.style.WARNING("No hay tickets para agrupar."))
            return

        logger.info(
            "Clusterización completada",
            extra={
                "requested_clusters": summary.requested_clusters,
                "effective_clusters": summary.effective_clusters,
                "total_tickets": summary.total_tickets,
                "assignments": summary.assignments,
                "duration_seconds": duration,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Clusterización completada: {count} tickets en {clusters} clústeres (solicitados {requested}).".format(
                    count=summary.total_tickets,
                    clusters=summary.effective_clusters,
                    requested=summary.requested_clusters,
                )
            )
        )
        self.stdout.write(f"  - Duración (s): {duration}")
        for cluster_id, amount in sorted(summary.assignments.items()):
            self.stdout.write(f"  - Cluster #{cluster_id}: {amount} tickets")
