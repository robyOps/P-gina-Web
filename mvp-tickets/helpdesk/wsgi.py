"""
- Propósito del módulo: publicar el callable WSGI de ``helpdesk`` para
  servidores sincronizados (Gunicorn, mod_wsgi).
- API pública: variable ``application`` conforme a la especificación WSGI.
- Flujo de datos: configuración de entorno → carga de ``helpdesk.settings`` →
  creación de la aplicación mediante ``get_wsgi_application``.
- Dependencias: ``os`` estándar y ``django.core.wsgi``.
- Decisiones clave y trade-offs: se inicializa settings en importación para que
  workers reusables compartan configuración sin costo adicional.
- Riesgos, supuestos, límites: espera que variables sensibles (SECRET_KEY,
  base de datos) se definan antes de levantar el servidor.
- Puntos de extensión: envolver ``application`` con middlewares WSGI adicionales
  (por ejemplo, medidores o proxies inversos).
"""

import os

from django.core.wsgi import get_wsgi_application

# Garantiza que el módulo de settings se configure si no viene de variables externas.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helpdesk.settings')

# Expone callable WSGI consumido por servidores compatibles.
application = get_wsgi_application()
