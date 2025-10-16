# Arquitectura de `reports`

## Contexto
App dedicada a generar reportes agregados y exportaciones de datos de tickets.

## Componentes
- `api.py`: vistas DRF que entregan métricas agregadas.
- `views.py`: vistas HTML/PDF para reportes gráficos.
- `models.py`: modelos placeholder para futuras extensiones.
- `admin.py`: registro mínimo en admin.

## Contratos
- Endpoints requieren permisos específicos (`reports.view_report`).
- Las vistas usan plantillas en `templates/reports/`.
- Exportaciones PDF/Excel se apoyan en utilidades de tickets y Django templates.

## Dependencias internas
- Depende de `tickets` para datos y cálculos.
- Usa `accounts` para validar roles.

## Diagrama ASCII
```
[API Reports] -> api.py -> services/tickets queries
[Dashboard] -> views.py -> templates/reports/*.html
```

## Reglas de límites
- No duplicar lógica de cálculo que exista en `tickets.services`; reutilizar funciones.
- Mantener exportaciones desacopladas de la capa web para permitir ejecuciones en background.
