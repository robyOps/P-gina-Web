"""
===============================================================================
Propósito:
    Definir la tabla de ruteo principal del proyecto, exponiendo vistas HTML,
    APIs REST y accesos administrativos.
API pública:
    ``urlpatterns`` consumido por Django para resolver rutas web y API.
Flujo de datos:
    Solicitudes entrantes → coincidencia con ``path`` → vistas en ``tickets``
    o ``catalog`` → respuestas HTML/JSON.
Dependencias:
    ``django.urls``, vistas de ``tickets`` y ``catalog``, y los módulos de
    autenticación de Django.
Decisiones:
    Se duplican rutas de auto-asignación (``auto-assign`` y ``rules``) para
    mantener retrocompatibilidad con URLs antiguas.
TODOs:
    TODO:PREGUNTA Confirmar si ambas rutas de auto-asignación deben convivir
    o si se puede consolidar en una sola convención.
===============================================================================
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
    path("login/",  auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    # --- Preferencias personales ---
    path("account/password/", account_views.password_change, name="account_password_change"),

    # --- UI (server-rendered) ---
    path("", ticket_views.dashboard, name="dashboard"),
    path("tickets/", ticket_views.tickets_home, name="tickets_home"),
    path("tickets/new/", ticket_views.ticket_create, name="ticket_create"),
    path("tickets/<int:pk>/", ticket_views.ticket_detail, name="ticket_detail"),
    path("tickets/<int:pk>/pdf/", ticket_views.ticket_pdf, name="ticket_pdf"),
    path("tickets/<int:pk>/assign/", ticket_views.ticket_assign, name="ticket_assign"),
    path(
        "tickets/<int:pk>/labels/<int:suggestion_id>/accept/",
        ticket_views.accept_label_suggestion,
        name="ticket_accept_suggestion",
    ),
    path("tickets/<int:pk>/update/", ticket_views.ticket_quick_update, name="ticket_quick_update"),
    path("tickets/<int:pk>/transition/", ticket_views.ticket_transition, name="ticket_transition"),
    path("notifications/", ticket_views.notifications_list, name="notifications_list"),
    path("faq/", ticket_views.faq_list, name="faq_list"),
    path("faq/<int:pk>/edit/", ticket_views.faq_edit, name="faq_edit"),
    path("faq/<int:pk>/delete/", ticket_views.faq_delete, name="faq_delete"),

    # Partials/acciones HTMX
    path("tickets/<int:pk>/discussion/partial/", ticket_views.discussion_partial, name="discussion_partial"),
    path("tickets/<int:pk>/comments/add/", ticket_views.add_comment, name="add_comment"),
    path("tickets/<int:pk>/audit/partial/", ticket_views.audit_partial, name="audit_partial"),

    path("logs/", ticket_views.logs_list, name="logs_list"),

    # Reportes
    path("reports/", ticket_views.reports_dashboard, name="reports_dashboard"),
    path("reports/check-sla/", ticket_views.reports_check_sla, name="reports_check_sla"),
    path("reports/export.pdf", ticket_views.reports_export_pdf, name="reports_export_pdf"),
    path("reports/export.xlsx", ticket_views.reports_export_excel, name="reports_export_excel"),


    # Mantenedor de usuarios (solo ADMINISTRADOR) → usamos el urls.py de accounts
    path("users/", include(("accounts.urls", "accounts"), namespace="accounts")),

    # Catálogo simple
    path("catalog/categories/", catalog_views.categories_list, name="categories_list"),
    path("catalog/categories/new/", catalog_views.category_create, name="category_create"),
    path("catalog/categories/<int:pk>/edit/", catalog_views.category_edit, name="category_edit"),

    path("catalog/subcategories/", catalog_views.subcategories_list, name="subcategories_list"),
    path("catalog/subcategories/new/", catalog_views.subcategory_create, name="subcategory_create"),
    path("catalog/subcategories/<int:pk>/edit/", catalog_views.subcategory_edit, name="subcategory_edit"),

    path("catalog/priorities/", catalog_views.priorities_list, name="priorities_list"),
    path("catalog/priorities/new/", catalog_views.priority_create, name="priority_create"),
    path("catalog/priorities/<int:pk>/edit/", catalog_views.priority_edit, name="priority_edit"),

    path("catalog/areas/", catalog_views.areas_list, name="areas_list"),
    path("catalog/areas/new/", catalog_views.area_create, name="area_create"),
    path("catalog/areas/<int:pk>/edit/", catalog_views.area_edit, name="area_edit"),

    # --- API bajo /api/ ---
    # PATH-FIREWALL: bloquear "/api" exacto y mantener API normal
    path("api", lambda request, *args, **kwargs: HttpResponseNotFound()),
    path("api/", include("helpdesk.api_urls")),
    path('api-auth/', include('rest_framework.urls')),

    path("auto-assign/", ticket_views.auto_rules_list, name="auto_rules_list"),
    path("auto-assign/new/", ticket_views.auto_rule_create, name="auto_rule_create"),
    path("auto-assign/<int:pk>/edit/", ticket_views.auto_rule_edit, name="auto_rule_edit"),
    path("auto-assign/<int:pk>/toggle/", ticket_views.auto_rule_toggle, name="auto_rule_toggle"),
    path("auto-assign/<int:pk>/delete/", ticket_views.auto_rule_delete, name="auto_rule_delete"),

    # --- Reglas de auto-asignación (ADMINISTRADOR) ---
    path("rules/",                ticket_views.auto_rules_list,   name="auto_rules_list"),
    path("rules/new/",            ticket_views.auto_rule_create,  name="auto_rule_create"),
    path("rules/<int:pk>/edit/",  ticket_views.auto_rule_edit,    name="auto_rule_edit"),
    path("rules/<int:pk>/toggle/",ticket_views.auto_rule_toggle,  name="auto_rule_toggle"),
    path("rules/<int:pk>/delete/",ticket_views.auto_rule_delete,  name="auto_rule_delete"),


    # Admin
path("admin/", admin.site.urls),
]

# Servir MEDIA en dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


handler404 = "helpdesk.views.redirect_to_safe_location"
handler500 = "helpdesk.views.handle_server_error"

