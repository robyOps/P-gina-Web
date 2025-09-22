from rest_framework import serializers
from .models import Ticket, TicketComment, TicketAttachment, TicketAssignment

class TicketSerializer(serializers.ModelSerializer):
    requester = serializers.HiddenField(default=serializers.CurrentUserDefault())
    code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "code", "title", "description",
            "category", "priority", "area", "kind",
            "status", "assigned_to",
            "created_at", "updated_at", "resolved_at", "closed_at",
            "requester",
        ]
        read_only_fields = ["assigned_to", "created_at", "updated_at", "resolved_at", "closed_at"]

class TicketCommentSerializer(serializers.ModelSerializer):
    author = serializers.HiddenField(default=serializers.CurrentUserDefault())
    class Meta:
        model = TicketComment
        fields = ["id", "ticket", "author", "body", "is_internal", "created_at"]
        read_only_fields = ["created_at"]

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
