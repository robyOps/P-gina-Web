from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Resource(models.Model):
    class ResourceType(models.TextChoices):
        ROOM = 'room', _('Sala')
        DEVICE = 'device', _('Equipo')
        OTHER = 'other', _('Otro')

    name = models.CharField(max_length=120, unique=True)
    type = models.CharField(max_length=16, choices=ResourceType.choices, default=ResourceType.OTHER)
    capacity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'booking_resource'


class Policy(models.Model):
    name = models.CharField(max_length=120, unique=True)
    max_hours = models.PositiveIntegerField(default=4)
    min_notice_hours = models.PositiveIntegerField(default=1)
    allow_weekends = models.BooleanField(default=True)
    buffer_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'booking_policy'


class Reservation(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'requested', _('Solicitada')
        APPROVED = 'approved', _('Aprobada')
        CANCELLED = 'cancelled', _('Cancelada')

    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='reservations')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reservations')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_reservation'
        ordering = ['-starts_at']
