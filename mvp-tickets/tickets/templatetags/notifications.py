from django import template
from ..models import Notification

register = template.Library()

@register.simple_tag(takes_context=True)
def unread_notifications_count(context):
    user = context['request'].user
    if user.is_authenticated:
        return Notification.objects.filter(user=user, is_read=False).count()
    return 0
