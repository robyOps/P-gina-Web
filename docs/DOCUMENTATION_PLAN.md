# Plan de documentación por prioridad

## Núcleo (Prioridad Alta)
- helpdesk/settings.py, helpdesk/urls.py, helpdesk/api_urls.py: Configuración y ruteo global.
- tickets/models.py, tickets/services.py, tickets/views.py, tickets/serializers.py: Dominio principal de tickets.
- accounts/permissions.py, accounts/roles.py, accounts/views.py, accounts/api.py: Gestión de acceso y API de cuentas.
- catalog/models.py, catalog/api.py, catalog/views.py: Definición de catálogo y exposición API.

## Soporte (Prioridad Media)
- tickets/utils.py, tickets/validators.py, tickets/signals.py, tickets/backfill.py.
- reports/api.py, reports/views.py: Capas de reporte.
- templates principales en templates/tickets/*.html y templates/accounts/*.html.
- scripts de gestión: accounts/management/commands/init_rbac.py, catalog/management/commands/seed_catalog.py, tickets/management/commands/*.

## Periférico (Prioridad Baja)
- Migraciones de cada app (solo agregar encabezados y notas de contexto).
- Tests en tickets/tests.
- Archivos administrativos (admin.py, apps.py) con notas breves.
- Documentos existentes (DEPLOYMENT.md) para referencias cruzadas.