from django.core.management.base import BaseCommand, CommandError

from tickets.clustering import train_ticket_clusters


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

        summary = train_ticket_clusters(num_clusters=clusters)

        if summary.total_tickets == 0:
            self.stdout.write(self.style.WARNING("No hay tickets para agrupar."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Clusterización completada: {count} tickets en {clusters} clústeres (solicitados {requested}).".format(
                    count=summary.total_tickets,
                    clusters=summary.effective_clusters,
                    requested=summary.requested_clusters,
                )
            )
        )
        for cluster_id, amount in sorted(summary.assignments.items()):
            self.stdout.write(f"  - Cluster #{cluster_id}: {amount} tickets")
