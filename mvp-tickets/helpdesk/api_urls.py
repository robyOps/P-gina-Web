from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.api import CategoryViewSet, PriorityViewSet, AreaViewSet
from accounts.api import MeView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from tickets.api import TicketViewSet
from reports.api import ReportSummaryView, ReportExportView

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
]

urlpatterns += [
    path("reports/summary/", ReportSummaryView.as_view(), name="reports_summary"),
    path("reports/export/", ReportExportView.as_view(), name="reports_export"),
]
