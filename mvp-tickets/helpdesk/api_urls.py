from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.api import CategoryViewSet, PriorityViewSet, AreaViewSet
from accounts.api import MeView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from tickets.api import (
    TicketViewSet,
    TicketSuggestionBulkRecomputeView,
    TicketClusterRetrainView,
    TicketAlertListView,
)
from reports.api import (
    ReportSummaryView,
    ReportExportView,
    ReportHeatmapView,
    ReportTopSubcategoriesView,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("priorities", PriorityViewSet, basename="priority")
router.register("areas", AreaViewSet, basename="area")
router.register("tickets", TicketViewSet, basename="ticket")

urlpatterns = [
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
]

urlpatterns += [
    path("reports/summary/", ReportSummaryView.as_view(), name="reports_summary"),
    path("reports/export/", ReportExportView.as_view(), name="reports_export"),
    path("reports/heatmap/", ReportHeatmapView.as_view(), name="reports_heatmap"),
    path("reports/subcategories/", ReportTopSubcategoriesView.as_view(), name="reports_subcategories"),
]
