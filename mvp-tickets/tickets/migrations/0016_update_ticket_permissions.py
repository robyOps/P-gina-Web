from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0015_alter_auditlog_action"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="ticket",
            options={
                "permissions": [
                    ("assign_ticket", "Puede asignar ticket"),
                    ("transition_ticket", "Puede cambiar estado de ticket"),
                    ("comment_internal", "Puede comentar internamente"),
                    ("view_all_tickets", "Puede ver todos los tickets"),
                    ("view_reports", "Puede ver reportes"),
                    ("manage_reports", "Puede administrar reportes"),
                ]
            },
        ),
    ]
