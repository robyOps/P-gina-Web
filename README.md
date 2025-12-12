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
| `ALLOWED_HOSTS` | Hosts permitidos | `[]` |
| `TICKET_LABEL_SUGGESTION_THRESHOLD` | Umbral mínimo de sugerencias | `0.35` |
| `AI_CHAT_API_URL` | Endpoint externo del proveedor de IA utilizado por el chatbot interno | `None` |
| `AI_CHAT_API_KEY` | Clave Bearer para autenticar las solicitudes hacia la API de IA | `None` |

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd mvp-tickets
python manage.py migrate
python manage.py createsuperuser  # opcional para acceder al admin
python manage.py runserver
```

## Carga rápida de datos demo (500 tickets)

El comando `load_demo_dataset` genera un set completo para probar KPIs, autoasignación
y reportes. Incluye catálogos, FAQs, reglas y usuarios de todos los roles.

1. Vacía los datos actuales y regenera la demo:

   ```bash
   cd mvp-tickets
   python manage.py migrate
   python manage.py load_demo_dataset --purge --tickets 500
   ```

   - `--purge` elimina tickets, catálogos demo, FAQs y usuarios de prueba previos
     (no toca superusuarios).
   - El comando ejecuta `init_rbac` automáticamente para refrescar grupos y permisos.

2. Usuarios listos para probar (clave: `Demo1234!`):
   - Administradores: `admin_ana`, `admin_bruno`
   - Técnicos: `tech_ale`, `tech_beto`
   - Solicitantes: `req_camila` (crítica), `req_diego`

3. Catálogos y reglas incluidas:
   - Categorías: Soporte Aplicaciones, Infraestructura, Seguridad, Dispositivos
   - Subcategorías por categoría (ERP, CRM, Pagos, VPN, WiFi, Correo, MFA, etc.)
   - Áreas: Operaciones, Tecnología, Finanzas, Dirección Ejecutiva y Experiencia Cliente
     (las dos últimas marcadas como críticas)
   - Reglas de autoasignación cruzando categoría, subcategoría y área (ej.: Seguridad/MFA → tech_ale;
     Dispositivos → tech_beto; Dirección Ejecutiva → tech_beto)
   - FAQs base ligadas a las categorías anteriores

4. KPIs después de la carga demo (500 tickets):
   - Abiertos: **160**
   - En progreso: **140**
   - Resueltos: **110**
   - Cerrados: **90**
   - Total: **500** tickets distribuidos en todas las categorías, áreas y prioridades

Re-ejecuta el comando cuando necesites regenerar datos frescos para validar reportes.

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
