from django.db import migrations


def grant_report_perms(apps, schema_editor):
    """Asigna los permisos de reportes a los grupos principales."""

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    from accounts.roles import ROLE_ADMIN, ROLE_TECH  # pylint: disable=import-outside-toplevel

    codes_by_group = {
        ROLE_ADMIN: {"view_reports", "manage_reports"},
        ROLE_TECH: {"view_reports"},
    }

    for group_name, codes in codes_by_group.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        perms = list(Permission.objects.filter(codename__in=codes))
        if perms:
            group.permissions.add(*perms)


def revoke_report_perms(apps, schema_editor):
    """Quita los permisos de reportes de los grupos si existen."""

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for group_name, code in (("ADMINISTRADOR", "view_reports"), ("ADMINISTRADOR", "manage_reports"), ("TECNICO", "view_reports")):
        try:
            group = Group.objects.get(name=group_name)
            perm = Permission.objects.get(codename=code)
        except (Group.DoesNotExist, Permission.DoesNotExist):
            continue
        group.permissions.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_ensure_tech_view_all"),
        ("tickets", "0016_update_ticket_permissions"),
    ]

    operations = [
        migrations.RunPython(grant_report_perms, revoke_report_perms),
    ]
