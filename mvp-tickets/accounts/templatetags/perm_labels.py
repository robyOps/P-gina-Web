from django import template
from accounts.permissions import PERMISSION_LABELS

register = template.Library()

@register.filter
def perm_label(permission):
    """Devuelve el nombre en español del permiso dado."""
    try:
        code = getattr(permission, "codename", "")
        return PERMISSION_LABELS.get(code, "")
    except Exception:
        return ""


@register.filter
def perm_known(perms):
    """Filtra una lista/queryset de permisos dejando solo los conocidos."""
    try:
        return [p for p in perms if getattr(p, "codename", "") in PERMISSION_LABELS]
    except Exception:
        return []
