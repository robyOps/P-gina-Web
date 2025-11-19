from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "area", "is_critical_actor")
    list_filter = ("area", "is_critical_actor")
    search_fields = ("user__username", "user__email")
