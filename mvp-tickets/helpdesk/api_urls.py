"""
Propósito:
    Registrar rutas REST públicas bajo ``/api/`` enlazándolas con las vistas correspondientes.
Qué expone:
    Un ``DefaultRouter`` para catálogos y tickets más rutas adicionales para filtros, alertas y reportes.
Permisos:
    Delegados completamente en las vistas; aquí solo se conectan endpoints ya protegidos.
Flujo de datos:
    HTTP → ``DefaultRouter``/``path`` → vistas → serializadores → JSON o archivos descargables.
Decisiones:
    Se retiraron rutas de clústeres y marcadores semánticos al quedar sin uso; solo permanecen filtros, alertas y reportes vigentes.
Riesgos:
    Toda ruta nueva debe registrarse también en la documentación para mantener trazabilidad con los clientes.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.api import CategoryViewSet, PriorityViewSet, AreaViewSet, SubcategoryViewSet
from accounts.api import MeView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from tickets.api import (
    TicketViewSet,
    TicketAlertListView,
    TicketFilterOptionsView,
    SubcategoryBackfillView,
)
from tickets.api_chat import ChatView
from reports.api import (
    ReportSummaryView,
    ReportExportView,
    ReportHeatmapView,
    ReportTopSubcategoriesView,
    ReportAreaBySubcategoryView,
    ReportAreaSubcategoryHeatmapView,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("priorities", PriorityViewSet, basename="priority")
router.register("areas", AreaViewSet, basename="area")
router.register("subcategories", SubcategoryViewSet, basename="subcategory")
router.register("tickets", TicketViewSet, basename="ticket")

urlpatterns = [
    path("filters/", TicketFilterOptionsView.as_view(), name="tickets_filters"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me/", MeView.as_view(), name="auth_me"),
    path("chat/", ChatView.as_view(), name="chatbot-ia"),
    path("", include(router.urls)),
    path(
        "tickets/alerts/",
        TicketAlertListView.as_view(),
        name="tickets_alerts",
    ),
    path(
        "backfill/subcategories/",
        SubcategoryBackfillView.as_view(),
        name="tickets_backfill_subcategories",
    ),
]

urlpatterns += [
    path("reports/summary/", ReportSummaryView.as_view(), name="reports_summary"),
    path("reports/export/", ReportExportView.as_view(), name="reports_export"),
    path("reports/heatmap/", ReportHeatmapView.as_view(), name="reports_heatmap"),
    path("reports/top-subcategories/", ReportTopSubcategoriesView.as_view(), name="reports_top_subcategories"),
    path("reports/area-by-subcategory/", ReportAreaBySubcategoryView.as_view(), name="reports_area_by_subcategory"),
    path("reports/heatmap-area-subcat/", ReportAreaSubcategoryHeatmapView.as_view(), name="reports_area_subcat_heatmap"),
]
