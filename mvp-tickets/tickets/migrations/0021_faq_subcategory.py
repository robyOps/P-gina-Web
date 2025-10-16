from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_subcategory"),
        ("tickets", "0020_ticket_subcategory"),
    ]

    operations = [
        migrations.AddField(
            model_name="faq",
            name="subcategory",
            field=models.ForeignKey(
                blank=True,
                help_text="Subclasificación opcional para afinar la segmentación de la respuesta.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="faqs",
                to="catalog.subcategory",
            ),
        ),
    ]
