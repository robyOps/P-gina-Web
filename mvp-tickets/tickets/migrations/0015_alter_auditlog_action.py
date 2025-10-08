from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0014_faq_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("CREATE", "Create Ticket"),
                    ("ASSIGN", "Assign/Reassign"),
                    ("UPDATE", "Update Ticket"),
                    ("STATUS", "Change Status"),
                    ("COMMENT", "Comment"),
                    ("ATTACH", "Attachment"),
                    ("SLA_WARN", "SLA Warning"),
                    ("SLA_BREACH", "SLA Breach"),
                ],
                max_length=20,
            ),
        ),
    ]
