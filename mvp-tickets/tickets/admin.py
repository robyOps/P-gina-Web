from django.contrib import admin

from .models_reservas import Resource, Policy, Reservation

admin.site.register(Resource)
admin.site.register(Policy)
admin.site.register(Reservation)
