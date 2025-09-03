from django import template
from accounts.permissions import PERMISSION_LABELS

register = template.Library()

@register.filter
def perm_label(permission):
    """Devuelve el nombre en español del permiso dado."""
    try:
        code = getattr(permission, "codename", "")
        return PERMISSION_LABELS.get(code, getattr(permission, "name", code))
    except Exception:
        return getattr(permission, "name", "")
