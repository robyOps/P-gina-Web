from django.apps import AppConfig

class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tickets"

    def ready(self):
        """Hook de arranque: registra señales del app de tickets."""
        # Importación lazy para evitar efectos secundarios al evaluar configuración.
        # Solo mantenemos señales relacionadas a tickets ya que el módulo de reservas fue removido.
        from . import signals  # noqa: F401
