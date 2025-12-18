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

### Criticidad y autoayuda

- Marca usuarios o áreas como críticos desde el admin (perfil de usuario y
  catálogo de áreas). Las acciones sobre tickets ejecutadas por ellos generan
  notificaciones adicionales a técnicos y administradores y se priorizan en las
  vistas de bandeja.
- Las FAQ admiten imagen y video (archivo MP4 o URL externa) para ilustrar las
  respuestas. Los campos opcionales aparecen en los formularios de alta/edición
  y muestran miniaturas en el listado.

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
| `DJANGO_ALLOWED_HOSTS` / `ALLOWED_HOSTS` | Hosts permitidos (coma separados) | `localhost,127.0.0.1,coyahuehelpdesk.duckdns.org` |
| `TICKET_LABEL_SUGGESTION_THRESHOLD` | Umbral mínimo de sugerencias | `0.35` |
| `AI_CHAT_API_URL` | Endpoint externo del proveedor de IA utilizado por el chatbot interno | `None` |
| `AI_CHAT_API_KEY` | Clave Bearer para autenticar las solicitudes hacia la API de IA | `None` |

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate
cd mvp-tickets
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser  # opcional para acceder al superadmin
python manage.py runserver
```

## Carga rápida de datos demo (seed realista)

El comando `seed_demo` genera un set reproducible de tickets entre
`2025-01-01` y `2025-12-12`, con logs distribuidos a lo largo del día, SLA con
vencimientos bajos (3–6% y casi siempre por poco), FAQs con multimedia,
autoasignaciones y notificaciones para áreas o actores críticos.

1. Preparar entorno y ejecutar el seed con los valores por defecto (600 tickets,
   fechas 2025-01-01 → 2025-12-12):

   ```bash
   cd mvp-tickets
   python manage.py migrate
   python manage.py load_demo_dataset --purge
   ```

   - `--reset` limpia datos de tickets/FAQs/reglas previos sin eliminar
     usuarios ni catálogos.
   - Usa `--seed 42` (por defecto) para obtener siempre la misma distribución.

2. Personaliza fechas y volúmenes según la prueba que necesites:

   ```bash
   python manage.py seed_demo \
     --start 2025-03-01 \
     --end 2025-12-12 \
     --tickets 800 \
     --seed 99
   ```

   - Ajusta `--tickets` para simular mayor carga en KPIs.
   - Cambia `--start`/`--end` para acotar la ventana temporal y generar más
     tickets recientes en progreso/abiertos.

3. Usuarios demo creados (clave: `Demo12345!`) incluyen perfiles críticos y
   roles asignados a grupos existentes. El comando asegura tickets RESUELTOS y
   CERRADOS en diciembre para dar contexto a los gráficos del dashboard.

## Pruebas de humo recomendadas

- `python manage.py check` → valida configuración.
- `python manage.py migrate --plan` → confirma migraciones aplicables.
- `python manage.py evaluate_ticket_alerts --dry-run --limit 5` → verifica que
  las tareas programadas se ejecuten sin efectos secundarios.

## Chatbot IA

- Configura las variables `AI_CHAT_API_URL` y `AI_CHAT_API_KEY` antes de iniciar
  el servidor para habilitar la comunicación con el proveedor externo de IA.
- El botón **Chatbot IA** aparece en la barra de navegación principal para
  usuarios autenticados. Al pulsarlo se despliega un panel flotante en la esquina
  inferior derecha sin abandonar la página actual.
- El chat envía peticiones `POST /api/chat/` con el mensaje del usuario y el
  backend genera el contexto seguro según el rol (solicitante, técnico o
  administrador) antes de invocar la API de IA.

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
