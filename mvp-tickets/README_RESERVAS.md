# Módulo de Reservas

## Checklist de verificación manual

1. Iniciar sesión en `/api-auth/login/`.
2. Crear una política en `/booking/politicas/` (ej: "Default").
3. Crear un recurso en `/booking/recursos/` (ej: "Sala 1").
4. Ir a `/booking/` y crear una reserva válida al menos 1 hora en el futuro.
5. Intentar una reserva solapada para el mismo recurso → debe mostrar mensaje de conflicto.
6. Consultar disponibilidad con el rango de la reserva creada y ver el evento listado.

## Pruebas automáticas

Ejecutar:

```bash
python manage.py test tickets.tests_reservas
```
