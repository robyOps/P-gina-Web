from rest_framework.routers import DefaultRouter
from .viewsets_reservas import ResourceViewSet, PolicyViewSet, ReservationViewSet

router = DefaultRouter()
router.register(r'resources', ResourceViewSet, basename='booking-resource')
router.register(r'policies', PolicyViewSet, basename='booking-policy')
router.register(r'reservations', ReservationViewSet, basename='booking-reservation')

urlpatterns = router.urls
