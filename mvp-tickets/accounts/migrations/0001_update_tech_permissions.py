"""Asegura que el rol de técnico pueda ver todos los tickets existentes."""

from django.db import migrations


def grant_view_all(apps, schema_editor):
    """Agrega el permiso ``view_all_tickets`` al grupo de técnicos."""

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        tech_group = Group.objects.get(name="TECNICO")
    except Group.DoesNotExist:
        return

    try:
        view_all = Permission.objects.get(codename="view_all_tickets")
    except Permission.DoesNotExist:
        return

    tech_group.permissions.add(view_all)


def revoke_view_all(apps, schema_editor):
    """Quita el permiso en caso de reversión manual."""

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        tech_group = Group.objects.get(name="TECNICO")
        view_all = Permission.objects.get(codename="view_all_tickets")
    except (Group.DoesNotExist, Permission.DoesNotExist):
        return

    tech_group.permissions.remove(view_all)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant_view_all, revoke_view_all),
    ]
