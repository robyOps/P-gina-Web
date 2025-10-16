"""
===============================================================================
Propósito:
    Exponer los endpoints REST del proyecto agrupando routers y vistas
    especializadas bajo el prefijo ``/api/``.
API pública:
    ``urlpatterns`` y ``router`` utilizados por Django REST Framework para
    montar viewsets y vistas basadas en clase.
Flujo de datos:
    Solicitudes HTTP → ``DefaultRouter``/``path`` → viewsets o vistas →
    serializadores → respuestas JSON.
Dependencias:
    ``rest_framework``, ``rest_framework_simplejwt`` y vistas propias de
    ``accounts``, ``catalog``, ``tickets`` y ``reports``.
Decisiones:
    Se combinan rutas del router con rutas manuales para exponer operaciones
    masivas y reportes sin duplicar lógica.
TODOs:
    TODO:PREGUNTA Validar si las rutas de reportes deberían versionarse o
    exponerse bajo un prefijo separado para contratos más estables.
===============================================================================
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.api import CategoryViewSet, PriorityViewSet, AreaViewSet, SubcategoryViewSet
from accounts.api import MeView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from tickets.api import (
    TicketViewSet,
    TicketSuggestionBulkRecomputeView,
    TicketClusterRetrainView,
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
        "tickets/retrain-clusters/",
        TicketClusterRetrainView.as_view(),
        name="tickets_retrain_clusters",
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
