from django.core.management.base import BaseCommand
from catalog.models import Priority

class Command(BaseCommand):
    help = "Crea prioridades por defecto"
    def handle(self, *args, **kwargs):
        defaults = [
            ("Baja", 72),
            ("Media", 48),
            ("Alta", 24),
            ("Crítica", 8),
        ]
        for name, hours in defaults:
            Priority.objects.get_or_create(name=name, defaults={"sla_hours": hours})
        self.stdout.write(self.style.SUCCESS("Prioridades listas"))
