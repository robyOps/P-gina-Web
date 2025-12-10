from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0025_autoassignrule_subcategory"),
    ]

    operations = [
        migrations.DeleteModel(name="TicketLabelSuggestion"),
        migrations.DeleteModel(name="TicketLabel"),
    ]
