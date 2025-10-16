# MVP Tickets

Mesa de ayuda construida con Django enfocada en gestión de tickets, catálogo de
servicios y reportes de desempeño. Este repositorio sirve como base de
referencia para continuar el desarrollo con énfasis en documentación.

## Visión general

El sistema se organiza en apps Django:

- `helpdesk`: configuración global y enrutamiento.
- `accounts`: administración de usuarios, roles y permisos.
- `catalog`: catálogo de categorías, subcategorías, prioridades y áreas.
- `tickets`: núcleo de negocio con modelos, servicios y APIs.
- `reports`: reportes y exportaciones.

### Diagrama ASCII de alto nivel

```
[Cliente]
   |
   v
helpdesk.urls --> views HTML (tickets/catalog)
   |
   +--> helpdesk.api_urls --> DRF (accounts/catalog/tickets/reports)
```

## Flujos críticos

1. **Creación de ticket**: usuario autenticado accede a `/tickets/new/`, el
   formulario envía datos a `TicketService.create_ticket`, se almacena en
   `tickets.models.Ticket` y se redirige al detalle.
2. **Auto asignación**: reglas en `tickets.management.commands` recalculan
   asignaciones utilizando `tickets.services.auto_assign`.
3. **Reportes**: consultas agregadas en `reports.api` que delegan en consultas a
   `tickets` y devuelven JSON o PDF.

## Dependencias

- Python 3.11+
- Django 5.2
- Django REST Framework
- Django Filter
- SimpleJWT
- django-cors-headers

## Variables de entorno relevantes

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `SECRET_KEY` | Clave secreta Django | `dev-insecure-change-me` |
| `DEBUG` | Modo depuración | `True` |
| `ALLOWED_HOSTS` | Hosts permitidos | `[]` |
| `TICKET_LABEL_SUGGESTION_THRESHOLD` | Umbral mínimo de sugerencias | `0.35` |

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd mvp-tickets
python manage.py migrate
python manage.py createsuperuser  # opcional para acceder al admin
python manage.py runserver
```

## Pruebas de humo recomendadas

- `python manage.py check` → valida configuración.
- `python manage.py migrate --plan` → confirma migraciones aplicables.
- `python manage.py evaluate_ticket_alerts --dry-run --limit 5` → verifica que
  las tareas programadas se ejecuten sin efectos secundarios.

## Límites y consideraciones

- `DEBUG` y CORS abierto están pensados solo para desarrollo.
- El almacenamiento de archivos se resuelve con el filesystem local; para prod
  usar S3 o equivalente.
- Los reportes PDF dependen de wkhtmltopdf o similar instalado en el host.
- TODO:PREGUNTA Confirmar motor de base de datos objetivo en producción.

## Recursos adicionales

- `docs/INVENTARIO.md`: lista completa de archivos y complejidad.
- `docs/DOCUMENTATION_PLAN.md`: plan de documentación por prioridad.
- `docs/TODO.md`: pendientes identificados durante la documentación.
