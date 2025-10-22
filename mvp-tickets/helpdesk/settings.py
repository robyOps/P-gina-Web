"""
- Propósito del módulo: centralizar la configuración del proyecto ``helpdesk``
  para que Django y DRF se inicialicen con valores seguros durante el
  desarrollo.
- API pública: constantes como ``INSTALLED_APPS``, ``MIDDLEWARE``,
  ``REST_FRAMEWORK`` y ``SIMPLE_JWT`` que son importadas por el runtime de
  Django y por utilidades internas.
- Flujo de datos: variables de entorno → casting en Python → consumo por
  componentes de Django (servidor HTTP, ORM, plantillas) y servicios externos
  como DRF o SimpleJWT.
- Dependencias: módulos estándar ``os`` y ``pathlib`` más paquetes Django,
  Django REST Framework, SimpleJWT, corsheaders y django-filter.
- Decisiones clave y trade-offs: se deja ``DEBUG`` activado y CORS abierto para
  acelerar iteraciones locales, se usa SQLite como persistencia por defecto y
  se obliga a contraseñas complejas mediante un validador propio.
- Riesgos, supuestos, límites: configuración pensada para ambiente local;
  requiere sobreescritura en producción de ``SECRET_KEY``, dominios, CORS y
  base de datos. TODO:PREGUNTA Definir dominios permitidos y política de tokens
  para entornos productivos.
- Puntos de extensión: variables alimentadas por ``os.environ`` y listas como
  ``INSTALLED_APPS`` o ``MIDDLEWARE`` permiten ser extendidas en settings
  específicos por ambiente.
"""

from pathlib import Path
from datetime import timedelta
import os

# Rutas base: punto de referencia para construir paths relativos a todo el proyecto.
BASE_DIR = Path(__file__).resolve().parent.parent

# ⚠️ Clave secreta; debe reemplazarse vía variable de entorno en producción para proteger sesiones y CSRF.
SECRET_KEY = "dev-insecure-change-me"
# Indicador de depuración que habilita mensajes detallados y renderers extra; se asume entorno local.
DEBUG = True
# Lista de hostnames autorizados; vacía para permitir localhost únicamente.
ALLOWED_HOSTS: list[str] = []

# Apps: orden define prioridades de carga y personalizaciones de cada módulo Django.
INSTALLED_APPS = [
    "django.contrib.admin",            # lo ocultaremos en prod
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Terceros
    "rest_framework",
    "django_filters",
    "corsheaders",
    "widget_tweaks",

    # Propias
    "accounts",
    "catalog",
    "tickets.apps.TicketsConfig",
    "reports",
]

# Middleware (CORS bien arriba)
# PATH-FIREWALL: registrar primero
MIDDLEWARE = [
    "helpdesk.middleware.PathFirewall",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "helpdesk.middleware.InputValidationMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Raíz de URL que Django usa para resolver rutas y vistas.
ROOT_URLCONF = "helpdesk.urls"

# Configuración de plantillas: carga archivos de ``templates`` y app directories.
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],   # ✅ así, con /
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# Punto de entrada WSGI requerido por servidores tradicionales (gunicorn, uwsgi).
WSGI_APPLICATION = "helpdesk.wsgi.application"

# DB (dev con SQLite; luego cambiamos a Postgres)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Validadores de password (puedes comentarlos en dev si estorban)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.ComplexPasswordValidator"},
]

# Idioma y zona para formateo y traducciones automáticas.
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# Static/Media (dev)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# DRF: solo JSON, JWT y filtros; controla autenticación y permisos globales de la API.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",   # <-- agrega esto
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "helpdesk.permissions.PrivilegedOnlyPermission",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ) if DEBUG else ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}

# SimpleJWT (tokens) controla expiraciones para sesiones basadas en tokens firmados.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# CORS (en prod, restringe dominios)
CORS_ALLOW_ALL_ORIGINS = True

# Field automático para claves primarias si los modelos no lo definen.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email (DEV)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # imprime emails en la consola del runserver
DEFAULT_FROM_EMAIL = "mvp@localhost"


# URLs de autenticación utilizadas por ``LoginRequiredMixin`` y helpers de Django.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
