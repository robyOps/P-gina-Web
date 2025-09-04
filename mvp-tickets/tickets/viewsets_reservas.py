from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models_reservas import Resource, Reservation, Policy
from .serializers_reservas import ResourceSerializer, ReservationSerializer, PolicySerializer
from .services_reservas import approve_reservation, cancel_reservation

# Intenta reutilizar permisos del proyecto; si no existen, define fallbacks.
try:
    from .permissions import IsStaffOrReadOnly as BaseIsAdminOrReadOnly, IsOwner as BaseIsOwner
except Exception:  # fallbacks seguros
    from rest_framework.permissions import BasePermission, SAFE_METHODS

    class BaseIsAdminOrReadOnly(BasePermission):
        def has_permission(self, request, view):
            if request.method in SAFE_METHODS:
                return True
            return bool(request.user and request.user.is_staff)

    class BaseIsOwner(BasePermission):
        def has_object_permission(self, request, view, obj):
            if request.user and request.user.is_staff:
                return True
            return getattr(obj, 'user_id', None) == getattr(request.user, 'id', None)


class ResourceViewSet(viewsets.ModelViewSet):
    queryset = Resource.objects.filter(is_active=True)
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated & BaseIsAdminOrReadOnly]


class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer
    permission_classes = [IsAuthenticated & BaseIsAdminOrReadOnly]


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.select_related('resource', 'user').all()
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated & BaseIsOwner]

    def get_queryset(self):
        qs = super().get_queryset()
        resource_id = self.request.query_params.get('resource_id')
        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        status_param = self.request.query_params.get('status')

        if resource_id:
            qs = qs.filter(resource_id=resource_id)
        if status_param:
            qs = qs.filter(status=status_param)
        if date_from:
            qs = qs.filter(ends_at__gte=date_from)
        if date_to:
            qs = qs.filter(starts_at__lte=date_to)
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        return qs

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        reservation = self.get_object()
        if not request.user.is_staff:
            return Response({"detail": "Solo administradores pueden aprobar."}, status=403)
        res = approve_reservation(reservation, request.user)
        return Response(ReservationSerializer(res).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        if not (request.user.is_staff or reservation.user_id == request.user.id):
            return Response({"detail": "No autorizado para cancelar."}, status=403)
        res = cancel_reservation(reservation, request.user)
        return Response(ReservationSerializer(res).data)

    @action(detail=False, methods=['get'])
    def availability(self, request):
        resource_id = request.query_params.get('resource_id')
        date_from = request.query_params.get('from')
        date_to = request.query_params.get('to')
        qs = Reservation.objects.select_related('resource').all()
        if resource_id:
            qs = qs.filter(resource_id=resource_id)
        if date_from:
            qs = qs.filter(ends_at__gte=date_from)
        if date_to:
            qs = qs.filter(starts_at__lte=date_to)
        data = [
            {
                "id": r.id,
                "title": f"{r.resource.name} ({r.get_status_display()})",
                "start": r.starts_at.isoformat(),
                "end": r.ends_at.isoformat(),
                "status": r.status,
            }
            for r in qs
        ]
        return Response(data)
