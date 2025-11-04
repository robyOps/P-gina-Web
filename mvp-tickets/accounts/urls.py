# accounts/urls.py
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.users_list, name="users_list"),
    path("new/", views.user_create, name="user_create"),
    path("<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("<int:pk>/toggle/", views.user_toggle, name="user_toggle"),
    path("<int:pk>/delete/", views.user_delete, name="user_delete"),
    path("roles/", views.roles_list, name="roles_list"),
    path("roles/new/", views.role_create, name="role_create"),
    path("roles/<int:pk>/edit/", views.role_edit, name="role_edit"),
    path("roles/<int:pk>/delete/", views.role_delete, name="role_delete"),
]



