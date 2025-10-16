# Arquitectura de `catalog`

## Contexto
App que gestiona categorías, subcategorías, prioridades y áreas utilizadas por los tickets.

## Componentes
- `models.py`: modelos `Category`, `Subcategory`, `Priority`, `Area`.
- `forms.py`: formularios administrativos.
- `views.py`: vistas server-rendered para mantenimiento.
- `api.py`: viewsets DRF para CRUD.
- `serializers.py`: serializadores de catálogo.
- `management/commands/seed_catalog.py`: script de carga inicial.

## Contratos
- Modelos relacionan `Category` → `Subcategory` y `Area`.
- APIs REST usan autenticación estándar y responden JSON paginado.
- Formularios esperan validaciones mínimas y se muestran en plantillas `templates/catalog/`.

## Dependencias internas
- Se relaciona con `tickets` a través de claves foráneas en modelos de ticket.
- Utiliza filtros y búsquedas de Django ORM.

## Diagrama ASCII
```
[Admin UI] -> views.py -> forms.py -> models.py
[API] -> api.py -> serializers.py -> models.py
[CLI] -> management/commands/seed_catalog.py -> models.py
```

## Reglas de límites
- No introducir lógica de tickets aquí; limitarse a catálogo.
- Mantener validaciones compartidas en `serializers.py`/`forms.py` para reutilización.
- Comandos de gestión deben ser idempotentes y seguros en múltiples ejecuciones.
