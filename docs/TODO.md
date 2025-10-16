# TODOs centralizados

## Configuración
- [helpdesk/settings.py] Definir dominios permitidos y política de rotación de tokens para producción (TODO:PREGUNTA).
- [README.md] Confirmar motor de base de datos objetivo para entornos productivos (TODO:PREGUNTA).
- [helpdesk/urls.py] Evaluar consolidación de rutas duplicadas de auto-asignación (TODO:PREGUNTA).
- [helpdesk/api_urls.py] Analizar necesidad de versionar o separar rutas de reportes (TODO:PREGUNTA).
- [accounts/forms.py] Definir reglas de complejidad de contraseña si se requieren (TODO:PREGUNTA).
- [accounts/api.py] Confirmar exposición de permisos además de grupos (TODO:PREGUNTA).
- [accounts/permissions.py] Evaluar permisos adicionales para reportes avanzados (TODO:PREGUNTA).
- [accounts/roles.py] Determinar si se requieren helpers para roles híbridos o jerárquicos (TODO:PREGUNTA).
- [accounts/management/commands/init_rbac.py] Confirmar si técnicos deben recibir permisos avanzados de reportes (TODO:PREGUNTA).
- [catalog/models.py] Confirmar impacto de la normalización en mayúsculas para integraciones externas (TODO:PREGUNTA).
- [catalog/api.py] Definir si técnicos pueden crear subcategorías desde la API (TODO:PREGUNTA).

## Documentación pendiente
- Completar documentación detallada de módulos restantes según `docs/DOCUMENTATION_PLAN.md`.
