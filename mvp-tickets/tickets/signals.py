# tickets/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction

from django.contrib.auth import get_user_model
from .models import Ticket, TicketComment, TicketAssignment, AuditLog, EventLog

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
        transaction.on_commit(_notify_created)
        return

    old = getattr(instance, "_old_status", None)
    if old == instance.status:
        return  # sin cambio real de estado → no notificar ni registrar

    if instance.status == Ticket.RESOLVED:
        transaction.on_commit(_notify_status_resolved)
    elif instance.status == Ticket.CLOSED:
        transaction.on_commit(_notify_status_closed)

    if getattr(instance, "_skip_status_signal_audit", False):
        return

    status_map = dict(Ticket.STATUS_CHOICES)
    AuditLog.objects.create(
        ticket=instance,
        actor=getattr(instance, "_status_changed_by", None),
        action="STATUS",
        meta={
            "from": old,
            "from_label": status_map.get(old),
            "to": instance.status,
            "to_label": status_map.get(instance.status),
            "with_comment": False,
            "internal": False,
            "comment_id": None,
            "body_preview": "",
        },
    )


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


@receiver(post_save, sender=AuditLog)
def on_audit_log(sender, instance: AuditLog, created, **kwargs):
    if not created:
        return
    messages = {
        "CREATE": "Ticket creado.",
        "ASSIGN": "Asignación de ticket.",
        "STATUS": "Cambio de estado del ticket.",
        "COMMENT": "Comentario en ticket.",
        "ATTACH": "Adjunto agregado al ticket.",
        "SLA_WARN": "Advertencia SLA.",
        "SLA_BREACH": "Incumplimiento SLA.",
    }

    meta = instance.meta or {}
    message = messages.get(instance.action, "")
    status_map = dict(Ticket.STATUS_CHOICES)

    def _username_from_meta(key_id: str, key_name: str) -> str:
        username = meta.get(key_name)
        if username:
            return username
        user_id = meta.get(key_id)
        if not user_id:
            return "Sin asignar"
        try:
            return (
                User.objects.only("username")
                .get(id=user_id)
                .username
            )
        except User.DoesNotExist:
            return "Sin asignar"

    if instance.action == "COMMENT":
        author = getattr(instance.actor, "username", "usuario")
        preview = (meta.get("body_preview") or "").strip()
        scope = "interno" if meta.get("internal") else "público"
        if preview:
            message = f"{author} comentó ({scope}): {preview}"
        else:
            message = f"{author} agregó un comentario {scope}."
        if meta.get("with_attachment"):
            filename = meta.get("filename") or "archivo adjunto"
            message += f" Adjuntó {filename}."
    elif instance.action == "ASSIGN":
        from_name = _username_from_meta("from", "from_username")
        to_name = _username_from_meta("to", "to_username")
        if meta.get("from") and meta.get("from") != meta.get("to"):
            message = f"Reasignado de {from_name} a {to_name}."
        else:
            message = f"Asignado a {to_name}."
        reason = (meta.get("reason") or "").strip()
        if reason:
            message += f" Motivo: {reason}."
        if meta.get("title_changed"):
            title_from = (meta.get("title_from") or "").strip()
            title_to = (meta.get("title_to") or "").strip()
            if title_from or title_to:
                message += f" Título: '{title_from or '—'}' → '{title_to or '—'}'."
    elif instance.action == "STATUS":
        from_label = meta.get("from_label") or status_map.get(meta.get("from"))
        to_label = meta.get("to_label") or status_map.get(meta.get("to"))
        from_label = from_label or "Sin estado"
        to_label = to_label or "Sin estado"
        message = f"Estado: {from_label} → {to_label}."
        if meta.get("with_comment"):
            preview = (meta.get("body_preview") or "").strip()
            if preview:
                scope = "interno" if meta.get("internal") else "público"
                message += f" Comentario {scope}: {preview}."
    elif instance.action == "ATTACH":
        filename = meta.get("filename")
        if filename:
            filename = filename.rsplit("/", 1)[-1]
            message = f"Adjunto agregado: {filename}."
        else:
            message = "Adjunto agregado al ticket."
    elif instance.action == "SLA_WARN":
        remaining = meta.get("remaining_h")
        if remaining is not None:
            message = f"Alerta SLA: {remaining}h restantes."
    elif instance.action == "SLA_BREACH":
        overdue = meta.get("overdue_h")
        if overdue is not None:
            message = f"SLA vencido hace {overdue}h."

    EventLog.objects.create(
        actor=instance.actor,
        model="ticket",
        obj_id=instance.ticket_id,
        action=instance.action,
        message=message,
    )
