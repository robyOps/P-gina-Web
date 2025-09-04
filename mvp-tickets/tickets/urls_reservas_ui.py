from django.urls import path
from .views_reservas_ui import booking_home, booking_resources, booking_policies

urlpatterns = [
    path('', booking_home, name='booking_ui_home'),
    path('recursos/', booking_resources, name='booking_ui_resources'),
    path('politicas/', booking_policies, name='booking_ui_policies'),
]
