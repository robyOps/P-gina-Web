"""
Propósito:
    Convertir modelos de tickets en estructuras JSON seguras para la API REST.
Qué expone:
    Serializadores de tickets, comentarios, adjuntos y asignaciones utilizadas por ``tickets.api``.
Permisos:
    La autorización se delega a las vistas; aquí se controlan campos de solo lectura para evitar abusos.
Flujo de datos:
    Modelos de Django → serializadores → JSON y viceversa durante operaciones de creación/actualización.
Decisiones:
    Se retiraron identificadores semánticos heredados del contrato público preservando la base de datos tal cual.
Riesgos:
    Cambios en catálogos externos (categoría, prioridad, área) pueden romper validaciones si no se sincronizan.
"""

from rest_framework import serializers
from catalog.models import Category, Priority

from .models import (
    Ticket,
    TicketComment,
    TicketAttachment,
    TicketAssignment,
)
from .utils import sanitize_text

class TicketSerializer(serializers.ModelSerializer):
    requester = serializers.HiddenField(default=serializers.CurrentUserDefault())
    code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "code", "title", "description",
            "category", "subcategory", "priority", "area", "kind",
            "status", "assigned_to",
            "created_at", "updated_at", "resolved_at", "closed_at",
            "requester",
        ]
        read_only_fields = [
            "assigned_to",
            "created_at",
            "updated_at",
            "resolved_at",
            "closed_at",
        ]

    def validate_title(self, value: str) -> str:
        cleaned = sanitize_text(value)
        if not cleaned:
            raise serializers.ValidationError("El título es obligatorio.")
        return cleaned

    def validate_description(self, value: str) -> str:
        cleaned = sanitize_text(value)
        if not cleaned:
            raise serializers.ValidationError("La descripción es obligatoria.")
        return cleaned

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None)

        can_choose_category = bool(user and user.has_perm("tickets.set_ticket_category"))
        can_choose_priority = bool(user and user.has_perm("tickets.set_ticket_priority"))
        can_choose_subcategory = bool(
            user and user.has_perm("tickets.set_ticket_subcategory")
        )
        can_choose_area = bool(user and user.has_perm("tickets.set_ticket_area"))

        if not can_choose_category:
            if self.instance is not None:
                attrs["category"] = getattr(self.instance, "category")
                attrs["subcategory"] = getattr(self.instance, "subcategory", None)
            else:
                default_category = (
                    Category.objects.filter(is_active=True).order_by("name").first()
                )
                if not default_category:
                    raise serializers.ValidationError(
                        {
                            "category": "No hay categorías disponibles. Contacta al administrador.",
                        }
                    )
                attrs["category"] = default_category
                attrs["subcategory"] = None
        elif not can_choose_subcategory:
            attrs["subcategory"] = None

        if not can_choose_priority:
            if self.instance is not None:
                attrs["priority"] = getattr(self.instance, "priority")
            else:
                default_priority = (
                    Priority.objects.order_by("sla_hours", "name").first()
                )
                if not default_priority:
                    raise serializers.ValidationError(
                        {
                            "priority": "No hay prioridades disponibles. Contacta al administrador.",
                        }
                    )
                attrs["priority"] = default_priority

        if not can_choose_area:
            if self.instance is not None:
                attrs["area"] = getattr(self.instance, "area")
            else:
                attrs["area"] = None

        category = attrs.get("category") or getattr(self.instance, "category", None)
        subcategory = attrs.get("subcategory")
        if subcategory is None and self.instance is not None:
            subcategory = getattr(self.instance, "subcategory", None)
        if (
            can_choose_category
            and can_choose_subcategory
            and category
            and subcategory
            and subcategory.category_id != category.id
        ):
            raise serializers.ValidationError(
                {"subcategory": "La subcategoría no pertenece a la categoría seleccionada."}
            )
        return attrs

class TicketCommentSerializer(serializers.ModelSerializer):
    author = serializers.HiddenField(default=serializers.CurrentUserDefault())
    class Meta:
        model = TicketComment
        fields = ["id", "ticket", "author", "body", "is_internal", "created_at"]
        read_only_fields = ["created_at"]

    def validate_body(self, value: str) -> str:
        cleaned = sanitize_text(value)
        if not cleaned:
            raise serializers.ValidationError("El comentario no puede estar vacío.")
        return cleaned

class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    class Meta:
        model = TicketAttachment
        fields = ["id", "ticket", "uploaded_by", "file", "content_type", "size", "uploaded_at"]
        read_only_fields = ["content_type", "size", "uploaded_at"]

class TicketAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketAssignment
        fields = ["id", "ticket", "from_user", "to_user", "reason", "created_at"]
        read_only_fields = ["from_user", "created_at"]


