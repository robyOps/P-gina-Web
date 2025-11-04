from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0022_alter_ticket_options"),
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
                    (
                        "set_ticket_category",
                        "Puede seleccionar la categoría al crear o actualizar un ticket",
                    ),
                    (
                        "set_ticket_priority",
                        "Puede seleccionar la prioridad al crear o actualizar un ticket",
                    ),
                    (
                        "set_ticket_subcategory",
                        "Puede seleccionar la subcategoría al crear o actualizar un ticket",
                    ),
                    (
                        "set_ticket_area",
                        "Puede seleccionar el área al crear o actualizar un ticket",
                    ),
                    (
                        "set_ticket_assignee",
                        "Puede elegir el técnico asignado al crear un ticket",
                    ),
                ]
            },
        ),
    ]
