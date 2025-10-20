"""
Propósito:
    Centralizar el enrutamiento de la API REST bajo ``/api/``.
API pública:
    ``router`` y ``urlpatterns`` que Django importa desde ``urls.py``.
Flujo de datos:
    HTTP → ``DefaultRouter``/``path`` → viewsets/vistas → serializadores → JSON/archivos.
Permisos:
    Delegados a las vistas; este módulo solo conecta rutas existentes sin ampliar alcance.
Decisiones de diseño:
    Se exponen rutas adicionales para recomputar sugerencias y reportes pero se
    retira la ruta de re-entrenamiento de clústeres al quedar obsoleta.
Riesgos:
    Cualquier ruta añadida aquí debe documentarse para mantener coherencia con la
    navegación y la documentación pública.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.api import CategoryViewSet, PriorityViewSet, AreaViewSet, SubcategoryViewSet
from accounts.api import MeView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from tickets.api import (
    TicketViewSet,
    TicketSuggestionBulkRecomputeView,
    TicketAlertListView,
    TicketFilterOptionsView,
    SubcategoryBackfillView,
)
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
    path("", include(router.urls)),
    path(
        "tickets/recompute-suggestions/",
        TicketSuggestionBulkRecomputeView.as_view(),
        name="tickets_recompute_suggestions",
    ),
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
