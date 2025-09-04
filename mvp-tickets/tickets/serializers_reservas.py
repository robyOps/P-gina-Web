from rest_framework import serializers
from .models_reservas import Resource, Reservation, Policy
from .services_reservas import create_reservation

try:  # Ticket es opcional según el proyecto
    from .models import Ticket
except Exception:  # pragma: no cover
    Ticket = None


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ['id', 'name', 'type', 'capacity', 'is_active']


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        fields = ['id', 'name', 'max_hours', 'min_notice_hours', 'allow_weekends', 'buffer_minutes']


class ReservationSerializer(serializers.ModelSerializer):
    resource = serializers.PrimaryKeyRelatedField(queryset=Resource.objects.filter(is_active=True))
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    if Ticket:
        ticket = serializers.PrimaryKeyRelatedField(
            queryset=Ticket.objects.all(), required=False, allow_null=True
        )

    class Meta:
        model = Reservation
        fields = [
            'id',
            'resource',
            'user',
            'starts_at',
            'ends_at',
            'status',
            'created_at',
            'updated_at',
            'ticket' if Ticket else None,
        ]
        fields = [f for f in fields if f]  # elimina None si no hay Ticket
        read_only_fields = ['status', 'created_at', 'updated_at']

    def create(self, validated_data):
        return create_reservation(
            user=validated_data['user'],
            resource=validated_data['resource'],
            starts_at=validated_data['starts_at'],
            ends_at=validated_data['ends_at'],
            ticket=validated_data.get('ticket'),
        )
