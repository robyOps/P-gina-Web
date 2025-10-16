from django.contrib import admin

from .models import EventLog, FAQ, TicketLabel, TicketLabelSuggestion


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
    list_display = ("question", "category", "created_by", "updated_by", "updated_at")
    search_fields = ("question", "answer")
    list_filter = ("category",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(TicketLabel)
class TicketLabelAdmin(admin.ModelAdmin):
    list_display = ("ticket", "name", "created_by", "created_at")
    list_filter = ("created_by",)
    search_fields = ("name", "ticket__code", "ticket__title")
    readonly_fields = ("created_at",)


@admin.register(TicketLabelSuggestion)
class TicketLabelSuggestionAdmin(admin.ModelAdmin):
    list_display = ("ticket", "label", "score", "is_accepted", "accepted_by", "updated_at")
    list_filter = ("is_accepted",)
    search_fields = ("label", "ticket__code", "ticket__title")
    readonly_fields = ("created_at", "updated_at", "accepted_at")
