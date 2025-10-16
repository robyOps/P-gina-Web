# MVP Tickets

Este repositorio contiene un ejemplo de mesa de ayuda construido con Django. El objetivo de esta rama es ofrecer un punto de partida limpio para continuar el desarrollo, sin archivos de pruebas residuales y con módulos documentados.

## Estructura

- `mvp-tickets/` proyecto Django principal con las apps `accounts`, `catalog`, `helpdesk`, `reports` y `tickets`.
- `templates/` archivos HTML base.
- `requirements.txt` dependencias mínimas para ejecutar el proyecto.

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Calidad del código

- Se eliminaron archivos de pruebas obsoletos (`tests.py`).
- Se refactorizaron las vistas del catálogo para reutilizar lógica y contar con comentarios descriptivos.
- Se documentaron los servicios de tickets para facilitar el mantenimiento.

Si vas a contribuir, sigue las convenciones existentes y agrega docstrings/comentarios claros cuando introduzcas nuevas piezas de negocio.

## Tareas programables

Todas las tareas se ejecutan con `python manage.py <comando>` y registran métricas básicas en STDOUT y en logs.

- `recompute_label_suggestions` &rarr; recalcula sugerencias de etiquetas. Opciones más relevantes:
  - `--only-open` procesa solo tickets abiertos/en progreso.
  - `--ticket-id <id>` se puede repetir para acotar tickets puntuales.
  - `--threshold 0.5` ajusta el umbral (0-1).
  - `--limit` y `--chunk-size` permiten controlar el volumen por lote.
  - Salida ejemplo:
    ```text
    Procesados 120 tickets (detectados 120).
      - Sugerencias creadas: 24
      - Sugerencias actualizadas: 80
      - Sugerencias eliminadas: 5
      - Umbral aplicado: 0.35
      - Duración (s): 2.1843
    ```
- `retrain_ticket_clusters` &rarr; reentrena clústeres de tickets (`--clusters` para indicar cantidad). Reporta duración y distribución.
- `evaluate_ticket_alerts` &rarr; evalúa advertencias/incumplimientos SLA (`--warn-ratio` y `--dry-run` disponibles). Mantiene idempotencia y no bloquea tráfico porque usa iteraciones en lotes.

## Endpoints REST

Todos los endpoints requieren autenticación JWT (`Authorization: Bearer <token>`). Las respuestas usan paginación por defecto de 20 elementos por página (parámetro `page` y `page_size` cuando aplique).

### Sugerencias de etiquetas por ticket

- `GET /api/tickets/{ticket_id}/suggestions/?status=pending` &rarr; lista sugerencias aceptadas o pendientes, junto con etiquetas confirmadas y umbral activo.
  ```json
  {
    "count": 3,
    "next": null,
    "previous": null,
    "results": [
      {"id": 10, "label": "VPN", "score": "0.82", "is_accepted": false}
    ],
    "meta": {
      "threshold": 0.35,
      "labels": [{"id": 4, "name": "Infraestructura"}]
    }
  }
  ```
- `POST /api/tickets/{ticket_id}/recompute-suggestions/` (solo técnicos/admin). Body opcional: `{ "threshold": 0.4 }`. Devuelve métricas del recalculo.
- `POST /api/tickets/{ticket_id}/suggestions/{suggestion_id}/accept/` &rarr; confirma una sugerencia. Respuesta incluye la sugerencia actualizada y la etiqueta creada.

### Operaciones masivas

- `POST /api/tickets/recompute-suggestions/` (admin). Body opcional:
  ```json
  {
    "ticket_ids": [1, 5, 9],
    "only_open": true,
    "threshold": 0.45,
    "limit": 500,
    "chunk_size": 200
  }
  ```
  Respuesta: `{ "detail": "Recomputo completado.", "metrics": { ... } }`.
- `POST /api/tickets/retrain-clusters/` (admin). Body `{ "clusters": 8 }`. Devuelve totales, clústeres efectivos, distribución y duración.

### Alertas y reportes

- `GET /api/tickets/alerts/?severity=warning&warn_ratio=0.75` devuelve tickets en estado de alerta con información SLA (paginado y resumen `{warnings, breaches}` al final).
- `GET /api/reports/heatmap/?from=2024-01-01&to=2024-01-31` (ya existente) entrega horas, días y matriz para construir mapas de calor.

En todos los casos la validación de roles se aplica automáticamente: administradores pueden operar globalmente, técnicos solo sobre sus tickets y solicitantes acceden únicamente a sus datos.
