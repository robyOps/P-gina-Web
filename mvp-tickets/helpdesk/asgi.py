"""
- Propósito del módulo: exponer el callable ASGI del proyecto ``helpdesk`` para
  servidores asincrónicos (Daphne, Uvicorn).
- API pública: variable ``application`` compatible con ASGI.
- Flujo de datos: variables de entorno → configuración Django → creación de la
  aplicación ASGI mediante ``get_asgi_application``.
- Dependencias: módulo estándar ``os`` y utilidades de ``django.core.asgi``.
- Decisiones clave y trade-offs: se fija ``DJANGO_SETTINGS_MODULE`` en tiempo de
  importación para garantizar inicialización consistente en workers.
- Riesgos, supuestos, límites: asume que settings por defecto son adecuados; en
  despliegues multitenant puede requerir wrapper adicional.
- Puntos de extensión: envolver ``application`` con middleware ASGI adicional o
  routers websockets antes de exponerlo.
"""

import os

from django.core.asgi import get_asgi_application

# Define módulo de settings por defecto si no se entregó vía entorno.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helpdesk.settings')

# Crea la instancia ASGI lista para ser consumida por el servidor.
application = get_asgi_application()
