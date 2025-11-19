# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_area_is_critical"),
        ("tickets", "0024_faq_image_faq_video_file_faq_video_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="autoassignrule",
            name="subcategory",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="auto_rules",
                to="catalog.subcategory",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="autoassignrule",
            name="uniq_auto_rule_cat_area",
        ),
        migrations.AddConstraint(
            model_name="autoassignrule",
            constraint=models.UniqueConstraint(
                fields=["category", "subcategory", "area"],
                name="uniq_auto_rule_cat_subcat_area",
            ),
        ),
    ]
