# accounts/roles.py
"""Constantes y helpers para roles de usuario."""

ROLE_ADMIN = "ADMINISTRADOR"
ROLE_TECH = "TECNICO"
ROLE_REQUESTER = "SOLICITANTE"


def is_admin(user):
    """True si es superusuario o pertenece al grupo ADMINISTRADOR."""
    return user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists()


def is_tech(user):
    """True si pertenece al grupo TECNICO."""
    return user.groups.filter(name=ROLE_TECH).exists()


def is_requester(user):
    """True si pertenece al grupo SOLICITANTE."""
    return user.groups.filter(name=ROLE_REQUESTER).exists()
