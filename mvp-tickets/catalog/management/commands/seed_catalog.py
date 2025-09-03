from django.core.management.base import BaseCommand
from catalog.models import Priority

class Command(BaseCommand):
    help = "Crea prioridades por defecto"
    def handle(self, *args, **kwargs):
        for key in ("LOW","MEDIUM","HIGH","CRITICAL"):
            Priority.objects.get_or_create(key=key)
        self.stdout.write(self.style.SUCCESS("Prioridades listas"))
