# tickets/templatetags/roles.py
from django import template
from accounts.roles import ROLE_ADMIN

register = template.Library()

@register.filter
def has_group(user, group_name: str) -> bool:
    """
    Uso en plantillas:
      {% if request.user|has_group:"ADMINISTRADOR" %} ... {% endif %}
    Devuelve True si el usuario pertenece al grupo dado.
    Para ADMIN, considera también superuser.
    """
    try:
        if not getattr(user, "is_authenticated", False):
            return False
        if group_name == ROLE_ADMIN:
            return user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists()
        return user.groups.filter(name=group_name).exists()
    except Exception:
        return False


@register.filter(name="add_class")
def add_class(bound_field, css_classes: str):
    """
    Añade clases CSS a un campo de form en la plantilla:
      {{ form.username|add_class:"border rounded px-3 py-2 w-full" }}
    Si no es un BoundField, lo devuelve tal cual.
    """
    try:
        widget = bound_field.field.widget
        existing = widget.attrs.get("class", "")
        merged = f"{existing} {css_classes}".strip() if existing else css_classes
        attrs = {**widget.attrs, "class": merged}
        return bound_field.as_widget(attrs=attrs)
    except Exception:
        return bound_field


@register.simple_tag(takes_context=True)
def can_access_admin_panel(context) -> bool:
    """Return True when the current user should see the admin shortcuts menu."""

    request = context.get("request")
    user = getattr(request, "user", None)

    if not getattr(user, "is_authenticated", False):
        return False

    if user.is_superuser or getattr(user, "is_staff", False):
        return True

    required_perms = [
        "auth.view_user",
        "auth.change_user",
        "auth.view_group",
        "auth.change_group",
        "catalog.view_category",
        "catalog.view_priority",
        "catalog.view_area",
        "tickets.view_autoassignrule",
        "tickets.view_eventlog",
        "admin.view_logentry",
    ]

    try:
        return any(user.has_perm(code) for code in required_perms)
    except Exception:
        return False
