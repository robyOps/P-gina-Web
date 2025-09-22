from django.contrib import admin

from .models import EventLog, FAQ


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    """Panel de solo lectura para rastrear actividades relevantes desde el admin."""

    list_display = ("created_at", "actor", "model", "obj_id", "action", "message")
    list_filter = ("model", "action")
    search_fields = ("message", "actor__username")
    readonly_fields = ("actor", "model", "obj_id", "action", "message", "resource_id", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "created_by", "updated_by", "updated_at")
    search_fields = ("question", "answer")
    readonly_fields = ("created_at", "updated_at")
