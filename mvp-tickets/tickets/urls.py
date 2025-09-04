from django.urls import path, include

urlpatterns = [
    path('reservas/', include('tickets.urls_reservas')),
]
