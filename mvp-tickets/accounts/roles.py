"""
===============================================================================
Propósito:
    Centralizar constantes y helpers para identificar roles de usuario.
API pública:
    Constantes ``ROLE_ADMIN``, ``ROLE_TECH``, ``ROLE_REQUESTER`` y funciones
    ``is_admin``, ``is_tech``, ``is_requester``.
Flujo de datos:
    Usuario Django → consultas a ``user.groups`` → booleano según pertenencia al
    grupo correspondiente.
Dependencias:
    Modelo de usuario configurado y grupos definidos en base de datos.
Decisiones:
    Se usan consultas directas a ``user.groups`` para mantener compatibilidad con
    el modelo estándar y evitar dependencias con permisos personalizados.
TODOs:
    TODO:PREGUNTA Confirmar si se requiere un helper para roles híbridos o
    jerárquicos (ej. supervisor técnico).
===============================================================================
"""

ROLE_ADMIN = "ADMINISTRADOR"
ROLE_TECH = "TECNICO"
ROLE_REQUESTER = "SOLICITANTE"


def is_admin(user):
    """Devuelve ``True`` si el usuario es superusuario o pertenece al grupo administrador."""

    return user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists()


def is_tech(user):
    """Devuelve ``True`` si el usuario pertenece al grupo técnico."""

    return user.groups.filter(name=ROLE_TECH).exists()


def is_requester(user):
    """Devuelve ``True`` si el usuario pertenece al grupo solicitante."""

    return user.groups.filter(name=ROLE_REQUESTER).exists()
