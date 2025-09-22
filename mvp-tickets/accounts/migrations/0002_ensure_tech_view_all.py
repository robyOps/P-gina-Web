"""Garantiza que el grupo TECNICO exista con los permisos operativos."""

from django.db import migrations


def ensure_tech_permissions(apps, schema_editor):
    """Crea/actualiza el grupo ``TECNICO`` con sus permisos operativos."""

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    from accounts.roles import ROLE_TECH  # pylint: disable=import-outside-toplevel
    from accounts.permissions import PERMISSION_TEMPLATES  # pylint: disable=import-outside-toplevel

    tech_group, _ = Group.objects.get_or_create(name=ROLE_TECH)

    tech_codenames = set(
        PERMISSION_TEMPLATES.get(ROLE_TECH, {}).get("codenames", [])
    )
    tech_codenames.add("view_all_tickets")

    permissions = list(
        Permission.objects.filter(codename__in=tech_codenames).only("id")
    )

    tech_group.permissions.add(*permissions)


def remove_view_all(apps, schema_editor):
    """Quita el permiso ``view_all_tickets`` del grupo ``TECNICO``."""

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        tech_group = Group.objects.get(name="TECNICO")
        view_all = Permission.objects.get(codename="view_all_tickets")
    except (Group.DoesNotExist, Permission.DoesNotExist):
        return

    tech_group.permissions.remove(view_all)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_update_tech_permissions"),
    ]

    operations = [
        migrations.RunPython(ensure_tech_permissions, remove_view_all),
    ]
