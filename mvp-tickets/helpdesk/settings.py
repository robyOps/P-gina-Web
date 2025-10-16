"""
===============================================================================
Propósito:
    Centralizar la configuración de Django para el proyecto ``helpdesk`` y
    definir valores por defecto seguros para desarrollo.
API pública:
    Variables de configuración importables por las apps (``INSTALLED_APPS``,
    ``REST_FRAMEWORK``, ``SIMPLE_JWT``, rutas de login, etc.).
Flujo de datos:
    Variables de entorno → constantes Python → componentes de Django y DRF
    que consumen estos ajustes durante el arranque.
Dependencias:
    ``django``, ``djangorestframework``, ``django-filter``,
    ``rest_framework_simplejwt``, ``corsheaders`` y utilidades estándar de
    Python.
Decisiones:
    Se habilita ``DEBUG`` y ``CORS_ALLOW_ALL_ORIGINS`` para entornos locales,
    se mantiene SQLite como base de datos de arranque y se fuerza un umbral
    mínimo para sugerencias de etiquetas.
TODOs:
    TODO:PREGUNTA Definir dominios permitidos y política de tokens para
    entornos productivos.
===============================================================================
"""

from pathlib import Path
from datetime import timedelta
import os

# Rutas base
BASE_DIR = Path(__file__).resolve().parent.parent

# ⚠️ En prod cambia esto y usa variables de entorno
SECRET_KEY = "dev-insecure-change-me"
DEBUG = True
ALLOWED_HOSTS: list[str] = []

# Apps
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
MIDDLEWARE = [
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

ROOT_URLCONF = "helpdesk.urls"

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

# Idioma y zona
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# Static/Media (dev)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# DRF: solo JSON, JWT y filtros
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


# SimpleJWT (tokens)
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# CORS (en prod, restringe dominios)
CORS_ALLOW_ALL_ORIGINS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email (DEV)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # imprime emails en la consola del runserver
DEFAULT_FROM_EMAIL = "mvp@localhost"


# Etiquetas sugeridas
_DEFAULT_LABEL_THRESHOLD = "0.35"
try:
    TICKET_LABEL_SUGGESTION_THRESHOLD = float(
        os.environ.get("TICKET_LABEL_SUGGESTION_THRESHOLD", _DEFAULT_LABEL_THRESHOLD)
    )
except ValueError:
    TICKET_LABEL_SUGGESTION_THRESHOLD = float(_DEFAULT_LABEL_THRESHOLD)


LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
