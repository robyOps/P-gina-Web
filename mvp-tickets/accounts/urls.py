# accounts/urls.py
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.users_list, name="users_list"),
    path("new/", views.user_create, name="user_create"),
    path("<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("<int:pk>/toggle/", views.user_toggle, name="user_toggle"),
]



