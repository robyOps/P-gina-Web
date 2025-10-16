from rest_framework import serializers
from .models import (
    Ticket,
    TicketComment,
    TicketAttachment,
    TicketAssignment,
    TicketLabel,
    TicketLabelSuggestion,
)
from .utils import sanitize_text

class TicketSerializer(serializers.ModelSerializer):
    requester = serializers.HiddenField(default=serializers.CurrentUserDefault())
    code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    cluster_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "code", "title", "description",
            "category", "subcategory", "priority", "area", "kind",
            "status", "assigned_to", "cluster_id",
            "created_at", "updated_at", "resolved_at", "closed_at",
            "requester",
        ]
        read_only_fields = [
            "assigned_to",
            "created_at",
            "updated_at",
            "resolved_at",
            "closed_at",
            "cluster_id",
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
        category = attrs.get("category") or getattr(self.instance, "category", None)
        subcategory = attrs.get("subcategory") or getattr(self.instance, "subcategory", None)
        if not subcategory:
            raise serializers.ValidationError({"subcategory": "La subcategoría es obligatoria."})
        if category and subcategory and subcategory.category_id != category.id:
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


class TicketLabelSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = TicketLabel
        fields = ["id", "ticket", "name", "created_by", "created_by_username", "created_at"]
        read_only_fields = ["ticket", "created_at", "created_by", "created_by_username"]


class TicketLabelSuggestionSerializer(serializers.ModelSerializer):
    accepted_by_username = serializers.CharField(source="accepted_by.username", read_only=True)

    class Meta:
        model = TicketLabelSuggestion
        fields = [
            "id",
            "ticket",
            "label",
            "score",
            "is_accepted",
            "accepted_by",
            "accepted_by_username",
            "accepted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "ticket",
            "accepted_by",
            "accepted_by_username",
            "accepted_at",
            "created_at",
            "updated_at",
        ]
