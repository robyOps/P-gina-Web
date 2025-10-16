# Arquitectura de `accounts`

## Contexto
App encargada de gestionar usuarios, roles y permisos para el helpdesk.

## Componentes
- `models.py`: placeholder para extensiones futuras del modelo de usuario.
- `forms.py`: formularios de creación/edición de usuarios y roles.
- `views.py`: vistas server-rendered para administrar cuentas.
- `api.py`: endpoints REST para información del usuario actual.
- `permissions.py`/`roles.py`: catálogo de permisos y plantillas de rol.
- `management/commands/init_rbac.py`: script para inicializar el RBAC.
- `templatetags/perm_labels.py`: filtros para representar permisos.

## Contratos
- Formularios esperan modelos `User` y `Group` estándar de Django.
- Vistas requieren permisos `auth.view_user`, `auth.add_user`, etc.
- API expone `GET /api/auth/me/` retornando información del usuario actual.

## Dependencias internas
- Reutiliza `tickets` para redirecciones y permisos cruzados.
- Plantillas en `templates/accounts/` para formularios y listados.

## Diagrama ASCII
```
[UI Admin] -> views.py -> forms.py -> Django ORM
                         \-> permissions.py (plantillas)
[API Auth] -> api.py -> serializers implícitos (Response manual)
```

## Reglas de límites
- No acceder directamente a lógica de tickets; usar servicios o permisos.
- Mantener plantillas de roles en un solo lugar (`roles.py`).
- Evitar dependencias circulares con `tickets` excepto por verificaciones de permisos.
