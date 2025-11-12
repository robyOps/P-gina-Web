from django.conf import settings
from django.db import migrations, models


def create_profiles(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Profile = apps.get_model('accounts', 'UserProfile')
    db_alias = schema_editor.connection.alias
    for user in User.objects.using(db_alias).all():
        Profile.objects.using(db_alias).get_or_create(user=user)


def remove_profiles(apps, schema_editor):
    Profile = apps.get_model('accounts', 'UserProfile')
    db_alias = schema_editor.connection.alias
    Profile.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_subcategory'),
        ('accounts', '0003_assign_report_permissions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rut', models.CharField(blank=True, help_text='RUT normalizado con guion (12345678-9).', max_length=12, null=True, unique=True)),
                ('area', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='user_profiles', to='catalog.area')),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Perfil de usuario',
                'verbose_name_plural': 'Perfiles de usuario',
            },
        ),
        migrations.RunPython(create_profiles, remove_profiles),
    ]
