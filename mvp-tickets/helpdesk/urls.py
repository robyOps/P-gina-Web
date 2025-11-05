"""
- Propósito del módulo: definir la tabla de ruteo principal del proyecto para
  exponer vistas HTML, endpoints API y la consola administrativa.
- API pública: variable ``urlpatterns`` con objetos ``path`` e ``include``
  consumidos por Django al resolver solicitudes.
- Flujo de datos: request entrante → coincidencia con patrón → ejecución de
  vista en ``tickets``, ``catalog`` o ``accounts`` → respuesta HTML/JSON.
- Dependencias: ``django.urls``, vistas importadas desde apps internas y
  configuraciones de autenticación de Django/DRF.
- Decisiones clave y trade-offs: se mantienen rutas duplicadas de auto-asignación
  para compatibilidad; se bloquea ``/api`` exacto para proteger el firewall
  de rutas; se delega la API REST a ``helpdesk.api_urls``.
- Riesgos, supuestos, límites: requiere middleware ``PathFirewall`` para evitar
  coincidencias ambiguas; se asume que permisos en vistas aplican controles.
- Puntos de extensión: pueden añadirse nuevas rutas importando vistas extras o
  extendiendo ``helpdesk.api_urls`` con ``include``.
- TODO:PREGUNTA Confirmar si ambas rutas de auto-asignación deben convivir o si
  se puede consolidar en una sola convención.
"""
from django.urls import path, include
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponseNotFound  # PATH-FIREWALL: importar respuesta 404

from tickets import views as ticket_views
from catalog import views as catalog_views
from accounts import views as account_views

urlpatterns = [
    # --- Auth web ---
    # Login para credenciales internas; no recibe parámetros dinámicos y renderiza formulario HTML.
    path("login/",  auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    # Cierra la sesión y redirige a ``login``; sin parámetros.
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    # --- Preferencias personales ---
    # Permite al usuario autenticado cambiar su contraseña actual.
    path("account/password/", account_views.password_change, name="account_password_change"),

    # --- UI (server-rendered) ---
    # Tablero inicial con indicadores del estado de la mesa de ayuda.
    path("", ticket_views.dashboard, name="dashboard"),
    # Listado con filtros de tickets visibles para el usuario.
    path("tickets/", ticket_views.tickets_home, name="tickets_home"),
    # Formulario de creación de ticket mediante POST validado.
    path("tickets/new/", ticket_views.ticket_create, name="ticket_create"),
    # Detalle completo del ticket identificado por ``pk``.
    path("tickets/<int:pk>/", ticket_views.ticket_detail, name="ticket_detail"),
    # Genera PDF del ticket ``pk``; salida binaria para descarga.
    path("tickets/<int:pk>/pdf/", ticket_views.ticket_pdf, name="ticket_pdf"),
    # Asignación manual del ticket ``pk`` a un agente o cola.
    path("tickets/<int:pk>/assign/", ticket_views.ticket_assign, name="ticket_assign"),
    # Actualización rápida de campos permitidos en ticket ``pk``.
    path("tickets/<int:pk>/update/", ticket_views.ticket_quick_update, name="ticket_quick_update"),
    # Transición de estado del ticket ``pk`` siguiendo el flujo definido.
    path("tickets/<int:pk>/transition/", ticket_views.ticket_transition, name="ticket_transition"),
    # Bandeja de notificaciones del usuario autenticado.
    path("notifications/", ticket_views.notifications_list, name="notifications_list"),
    # Listado de preguntas frecuentes visibles para soporte.
    path("faq/", ticket_views.faq_list, name="faq_list"),
    # Permite editar la FAQ identificada por ``pk``.
    path("faq/<int:pk>/edit/", ticket_views.faq_edit, name="faq_edit"),
    # Elimina la FAQ ``pk`` aplicando reglas de negocio internas.
    path("faq/<int:pk>/delete/", ticket_views.faq_delete, name="faq_delete"),
    # Sesión dedicada para conversar con el asistente de IA.
    path("chat/", ticket_views.chat_session, name="chat_session"),

    # Partials/acciones HTMX
    # Devuelve fragmento de discusión para inyectar en modal o panel.
    path("tickets/<int:pk>/discussion/partial/", ticket_views.discussion_partial, name="discussion_partial"),
    # Crea un comentario asociado al ticket ``pk``; puede disparar notificaciones.
    path("tickets/<int:pk>/comments/add/", ticket_views.add_comment, name="add_comment"),
    # Renderiza auditoría del ticket ``pk`` con entradas recientes.
    path("tickets/<int:pk>/audit/partial/", ticket_views.audit_partial, name="audit_partial"),

    # Lista eventos de bitácora del sistema para usuarios con permisos elevados.
    path("logs/", ticket_views.logs_list, name="logs_list"),

    # Reportes
    # Dashboard de reportes agregados y filtros de negocio.
    path("reports/", ticket_views.reports_dashboard, name="reports_dashboard"),
    # Evalúa cumplimiento de SLA y devuelve resultados tabulares.
    path("reports/check-sla/", ticket_views.reports_check_sla, name="reports_check_sla"),
    # Exporta reporte actual a PDF; carga intensiva según volumen de tickets.
    path("reports/export.pdf", ticket_views.reports_export_pdf, name="reports_export_pdf"),
    # Exporta reporte actual a Excel para análisis externo.
    path("reports/export.xlsx", ticket_views.reports_export_excel, name="reports_export_excel"),


    # Mantenedor de usuarios (solo ADMINISTRADOR) → usamos el urls.py de accounts
    # Entrypoint para CRUD de usuarios y roles; requiere staff con permisos adecuados.
    path("users/", include(("accounts.urls", "accounts"), namespace="accounts")),

    # Catálogo simple
    # Lista categorías del catálogo de servicios.
    path("catalog/categories/", catalog_views.categories_list, name="categories_list"),
    # Crea una nueva categoría con validaciones de negocio.
    path("catalog/categories/new/", catalog_views.category_create, name="category_create"),
    # Edita la categoría ``pk``.
    path("catalog/categories/<int:pk>/edit/", catalog_views.category_edit, name="category_edit"),
    # Elimina la categoría ``pk``.
    path("catalog/categories/<int:pk>/delete/", catalog_views.category_delete, name="category_delete"),

    # Lista subcategorías disponibles.
    path("catalog/subcategories/", catalog_views.subcategories_list, name="subcategories_list"),
    # Crea una nueva subcategoría.
    path("catalog/subcategories/new/", catalog_views.subcategory_create, name="subcategory_create"),
    # Edita subcategoría ``pk`` con validaciones jerárquicas.
    path("catalog/subcategories/<int:pk>/edit/", catalog_views.subcategory_edit, name="subcategory_edit"),
    # Elimina subcategoría ``pk``.
    path("catalog/subcategories/<int:pk>/delete/", catalog_views.subcategory_delete, name="subcategory_delete"),

    # Lista prioridades configuradas para SLA.
    path("catalog/priorities/", catalog_views.priorities_list, name="priorities_list"),
    # Crea prioridad con parámetros de severidad.
    path("catalog/priorities/new/", catalog_views.priority_create, name="priority_create"),
    # Edita prioridad ``pk`` para ajustar tiempos.
    path("catalog/priorities/<int:pk>/edit/", catalog_views.priority_edit, name="priority_edit"),
    # Elimina prioridad ``pk``.
    path("catalog/priorities/<int:pk>/delete/", catalog_views.priority_delete, name="priority_delete"),

    # Lista áreas organizacionales.
    path("catalog/areas/", catalog_views.areas_list, name="areas_list"),
    # Crea nueva área de atención.
    path("catalog/areas/new/", catalog_views.area_create, name="area_create"),
    # Edita área ``pk`` vinculada a tickets.
    path("catalog/areas/<int:pk>/edit/", catalog_views.area_edit, name="area_edit"),
    # Elimina área ``pk``.
    path("catalog/areas/<int:pk>/delete/", catalog_views.area_delete, name="area_delete"),

    # --- API bajo /api/ ---
    # PATH-FIREWALL: bloquear "/api" exacto y mantener API normal
    # Protege contra enumeración del árbol API sin slash final devolviendo 404 explícito.
    path("api", lambda request, *args, **kwargs: HttpResponseNotFound()),
    # Expone endpoints REST agrupados en ``helpdesk.api_urls``.
    path("api/", include("helpdesk.api_urls")),
    # Endpoint auxiliar para autenticación en el navegador del DRF.
    path('api-auth/', include('rest_framework.urls')),

    # --- Auto-asignación legacy ---
    # Listado histórico de reglas de auto-asignación.
    path("auto-assign/", ticket_views.auto_rules_list, name="auto_rules_list"),
    # Crea regla legacy para routing automático.
    path("auto-assign/new/", ticket_views.auto_rule_create, name="auto_rule_create"),
    # Edita regla legacy ``pk``.
    path("auto-assign/<int:pk>/edit/", ticket_views.auto_rule_edit, name="auto_rule_edit"),
    # Alterna estado activo/inactivo de regla legacy ``pk``.
    path("auto-assign/<int:pk>/toggle/", ticket_views.auto_rule_toggle, name="auto_rule_toggle"),
    # Elimina regla legacy ``pk``.
    path("auto-assign/<int:pk>/delete/", ticket_views.auto_rule_delete, name="auto_rule_delete"),

    # --- Reglas de auto-asignación (ADMINISTRADOR) ---
    # Listado principal de reglas vigente.
    path("rules/",                ticket_views.auto_rules_list,   name="auto_rules_list"),
    # Crea regla vigente.
    path("rules/new/",            ticket_views.auto_rule_create,  name="auto_rule_create"),
    # Edita regla vigente ``pk``.
    path("rules/<int:pk>/edit/",  ticket_views.auto_rule_edit,    name="auto_rule_edit"),
    # Alterna estado de regla vigente ``pk``.
    path("rules/<int:pk>/toggle/",ticket_views.auto_rule_toggle,  name="auto_rule_toggle"),
    # Elimina regla vigente ``pk`` con validaciones.
    path("rules/<int:pk>/delete/",ticket_views.auto_rule_delete,  name="auto_rule_delete"),


    # Admin
    # Portal de administración para superusuarios; sin parámetros dinámicos.
    path("admin/", admin.site.urls),
]

# Servir MEDIA en dev; usa filesystem local solo cuando ``DEBUG`` está activo.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# Redirige rutas no encontradas a ubicación segura definida en vistas personalizadas.
handler404 = "helpdesk.views.redirect_to_safe_location"
# Captura errores 500 y muestra plantilla amigable sin filtrar trazas sensibles.
handler500 = "helpdesk.views.handle_server_error"

