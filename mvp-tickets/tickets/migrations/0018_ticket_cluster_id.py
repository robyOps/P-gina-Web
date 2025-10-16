# Generated manually for cluster_id field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0017_ticketlabel_ticketlabelsuggestion"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="cluster_id",
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
    ]
