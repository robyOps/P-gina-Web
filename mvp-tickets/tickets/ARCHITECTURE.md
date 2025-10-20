# Arquitectura de `tickets`

## Contexto
App núcleo que maneja creación, seguimiento, asignación y análisis de tickets.

## Componentes
- `models.py`: entidades de ticket, comentarios, FAQ, alertas.
- `serializers.py`: serializadores DRF para operaciones API.
- `views.py`: vistas server-rendered para panel y detalle.
- `services.py`: lógica de negocio desacoplada de vistas.
- `utils.py`, `validators.py`, `timezones.py`: utilidades complementarias.
- `management/commands/*`: tareas programadas (SLA, notificaciones).
- `tests/`: pruebas del API y analítica.

## Contratos
- Modelos exponen métodos para transiciones de estado y cálculo de métricas.
- Servicios consumen modelos y devuelven resultados deterministas (sin efectos secundarios inesperados).
- APIs siguen convención REST, autenticación JWT y permisos basados en roles.

## Dependencias internas
- Consume catálogo para categorías y subcategorías.
- Reutiliza cuentas para permisos y asignaciones de usuarios.
- Usa plantillas `templates/tickets/` para HTML.

## Diagrama ASCII
```
[UI] -> views.py -> services.py -> models.py
[API] -> api.py -> serializers.py -> models.py
[Jobs] -> management/commands/*.py -> services.py/models.py
```

## Reglas de límites
- Mantener reglas de negocio dentro de `services.py`/modelos, no en vistas.
- Compartir utilidades comunes en `utils.py` para evitar duplicidad.
- Tests deben cubrir casos de transición y métricas críticas.
