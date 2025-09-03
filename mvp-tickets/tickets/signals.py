# tickets/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction

from django.contrib.auth import get_user_model
from .models import Ticket, TicketComment, TicketAssignment

User = get_user_model()


def _email_of(user):
    return (getattr(user, "email", None) or "").strip()


# ----- Guardamos el estado anterior para comparar en post_save -----
@receiver(pre_save, sender=Ticket)
def _stash_old_status(sender, instance: Ticket, **kwargs):
    if instance.pk:
        try:
            instance._old_status = sender.objects.only("status").get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Ticket)
def on_ticket_created_or_updated(sender, instance: Ticket, created, **kwargs):
    """
    Notifica:
      - creado → requester
      - cambio a RESOLVED → requester
      - cambio a CLOSED → requester
    (evita re-notificar si el estado no cambió)
    """
    def _notify_created():
        to = [_email_of(instance.requester)]
        if to[0]:
            send_mail(
                subject=f"[{instance.code}] Ticket creado",
                message=f"Se creó tu ticket:\n\nTítulo: {instance.title}\nEstado: {instance.status}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=to,
                fail_silently=True,
            )

    def _notify_status_resolved():
        to = [_email_of(instance.requester)]
        if to[0]:
            send_mail(
                subject=f"[{instance.code}] Ticket resuelto",
                message="Tu ticket fue marcado como RESUELTO. Por favor valida.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=to,
                fail_silently=True,
            )

    def _notify_status_closed():
        to = [_email_of(instance.requester)]
        if to[0]:
            send_mail(
                subject=f"[{instance.code}] Ticket cerrado",
                message="Tu ticket ha sido CERRADO. ¡Gracias!",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=to,
                fail_silently=True,
            )

    # Ejecuta después del commit de DB (evita enviar si falla la transacción)
    if created:
        return transaction.on_commit(_notify_created)

    old = getattr(instance, "_old_status", None)
    if old == instance.status:
        return  # sin cambio real de estado → no notificar

    if instance.status == Ticket.RESOLVED:
        return transaction.on_commit(_notify_status_resolved)

    if instance.status == Ticket.CLOSED:
        return transaction.on_commit(_notify_status_closed)


@receiver(post_save, sender=TicketAssignment)
def on_assignment(sender, instance: TicketAssignment, created, **kwargs):
    """
    Notifica al técnico asignado solo cuando se crea el registro de asignación.
    """
    if not created:
        return

    def _notify():
        to = [_email_of(instance.to_user)]
        if to[0]:
            send_mail(
                subject=f"[{instance.ticket.code}] Nuevo ticket asignado",
                message=f"Se te asignó el ticket {instance.ticket.code}\nMotivo: {instance.reason or '-'}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=to,
                fail_silently=True,
            )

    transaction.on_commit(_notify)


@receiver(post_save, sender=TicketComment)
def on_public_comment(sender, instance: TicketComment, created, **kwargs):
    """
    Notifica al requester SOLO por comentarios públicos.
    """
    if not created or instance.is_internal:
        return

    def _notify():
        to = [_email_of(instance.ticket.requester)]
        if to[0]:
            send_mail(
                subject=f"[{instance.ticket.code}] Nuevo comentario",
                message=f"{instance.author.username} comentó:\n\n{instance.body}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=to,
                fail_silently=True,
            )

    transaction.on_commit(_notify)
