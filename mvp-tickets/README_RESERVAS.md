# Módulo de Reservas

## Checklist de verificación manual

1. Iniciar sesión en `/api-auth/login/`.
2. Crear una política en `/booking/politicas/` (ej: "Default").
3. Crear un recurso en `/booking/recursos/` (ej: "Sala 1").
4. Ir a `/booking/` y crear una reserva válida al menos 1 hora en el futuro.
5. Intentar una reserva solapada para el mismo recurso → debe mostrar mensaje de conflicto.
6. Consultar disponibilidad con el rango de la reserva creada y ver el evento listado.

## Ayuda para nuevos usuarios

- Los campos de fecha/hora usan el control `datetime-local`. Haz clic en el campo para seleccionar tanto la fecha como la hora y los minutos en formato de 24 horas.
- Si aparece el mensaje "La reserva no cumple las políticas", verifica que:
  - La hora de inicio sea futura y respete el aviso mínimo configurado.
  - La duración no exceda el máximo permitido.
  - El día no sea fin de semana cuando las políticas lo prohíben.
  - No existan otras reservas solapadas para el mismo recurso.

## Pruebas automáticas

Ejecutar:

```bash
python manage.py test tickets.tests_reservas
```
