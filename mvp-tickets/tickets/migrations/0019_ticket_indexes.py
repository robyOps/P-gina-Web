from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0018_ticket_cluster_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ticket",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AddIndex(
            model_name="ticketlabel",
            index=models.Index(fields=["name"], name="ticketlabel_name_idx"),
        ),
    ]
