from django.contrib import admin

from .models_reservas import Resource, Policy, Reservation
from .models import EventLog

admin.site.register(Resource)
admin.site.register(Policy)
admin.site.register(Reservation)
admin.site.register(EventLog)
