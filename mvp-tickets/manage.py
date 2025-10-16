#!/usr/bin/env python
"""
- Propósito del módulo: exponer punto de entrada CLI para gestionar el proyecto
  ``helpdesk`` (migraciones, runserver, comandos custom).
- API pública: función ``main`` invocable desde ``__main__``.
- Flujo de datos: variables de entorno → selección de settings → ejecución de
  ``execute_from_command_line`` con argumentos del sistema.
- Dependencias: ``os``, ``sys`` y ``django.core.management``.
- Decisiones clave y trade-offs: encapsula la importación de Django en try/except
  para mostrar error amigable cuando falta el paquete.
- Riesgos, supuestos, límites: requiere que el entorno virtual tenga Django y
  que ``DJANGO_SETTINGS_MODULE`` apunte a ``helpdesk.settings``.
- Puntos de extensión: función ``main`` puede envolverse para setear variables
  adicionales antes de delegar en Django.
"""
import os
import sys


def main():
    """Ejecuta tareas administrativas de Django.

    Args:
      None: los argumentos se leen directamente desde ``sys.argv``.

    Returns:
      None: la función delega el flujo al comando solicitado.

    Raises:
      ImportError: si Django no está instalado o no se encuentra en ``PYTHONPATH``.

    Complejidad:
      O(n) respecto al número de argumentos procesados por Django.

    Ejemplo:
      >>> main()  # doctest: +SKIP
    """
    # Configura settings por defecto si la variable no está definida al invocar el script.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helpdesk.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Mensaje extendido para facilitar diagnóstico cuando falta la dependencia.
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
