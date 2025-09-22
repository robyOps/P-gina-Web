# tickets/services.py
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import AuditLog, Ticket, AutoAssignRule, TicketAssignment, Notification
from django.db.models import Q
from openpyxl import Workbook
from accounts.roles import ROLE_TECH, ROLE_ADMIN

User = get_user_model()

def _has_log(t, action: str) -> bool:
    return AuditLog.objects.filter(ticket=t, action=action).exists()

def run_sla_check(*, warn_ratio: float = 0.8, dry_run: bool = False) -> dict:
    """
    Revisa tickets OPEN/IN_PROGRESS y:
      - Emite SLA_WARN cuando el tiempo transcurrido >= (warn_ratio * sla_hours)
      - Emite SLA_BREACH cuando supera el SLA
      - Si ya está RESOLVED, registra BREACH si se resolvió después del due_at
    Envía emails (consola en dev) y registra AuditLog, a menos que dry_run=True.
    Devuelve: {'warnings': N, 'breaches': M}
    """
    now = timezone.now()
    open_like = [Ticket.OPEN, Ticket.IN_PROGRESS]
    qs = (Ticket.objects
          .select_related("priority", "requester", "assigned_to")
          .filter(status__in=open_like))

    warned = breached = 0

    role_users = []
    if not dry_run:
        role_users = list(
            User.objects.filter(
                is_active=True, groups__name__in=[ROLE_TECH, ROLE_ADMIN]
            ).distinct()
        )

    for t in qs:
        sla_hours = t.sla_hours_value
        due = t.due_at
        elapsed_h = (now - t.created_at).total_seconds() / 3600.0
        warn_th = sla_hours * warn_ratio

        # Si se resolvió: breach si se resolvió luego del due
        if t.resolved_at:
            if t.resolved_at > due and not _has_log(t, "SLA_BREACH"):
                if not dry_run:
                    AuditLog.objects.create(ticket=t, actor=None, action="SLA_BREACH",
                                            meta={"due_at": due.isoformat(), "resolved_at": t.resolved_at.isoformat()})
                    _email_breach(t, role_users)
                breached += 1
            continue

        # Aún no resuelto: breach
        if elapsed_h >= sla_hours and not _has_log(t, "SLA_BREACH"):
            if not dry_run:
                AuditLog.objects.create(ticket=t, actor=None, action="SLA_BREACH",
                                        meta={"due_at": due.isoformat(), "overdue_h": int((now - due).total_seconds() // 3600)})
                _email_breach(t, role_users)
            breached += 1
            continue

        # Warning
        if elapsed_h >= warn_th and not _has_log(t, "SLA_WARN"):
            if not dry_run:
                AuditLog.objects.create(ticket=t, actor=None, action="SLA_WARN",
                                        meta={"due_at": due.isoformat(), "remaining_h": int((due - now).total_seconds() // 3600)})
                _email_warn(t, role_users)
            warned += 1

    return {"warnings": warned, "breaches": breached}


def _create_notifications(users, message: str, ticket: Ticket):
    link = reverse("ticket_detail", args=[ticket.pk])
    notifications = [Notification(user=user, message=message, url=link) for user in users]
    if notifications:
        Notification.objects.bulk_create(notifications)


def _email_warn(t: Ticket, role_users):
    recipients = {user for user in role_users if user}
    if t.assigned_to and t.assigned_to.is_active:
        recipients.add(t.assigned_to)
    recipients = {u for u in recipients if getattr(u, "is_active", False)}
    emails = [getattr(u, "email", None) for u in recipients]
    emails = [email for email in emails if email]
    if emails:
        send_mail(
            subject=f"[{t.code}] SLA por vencer",
            message=f"El ticket {t.code} ({t.title}) está por vencer su SLA.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            fail_silently=True,
        )
    if recipients:
        _create_notifications(
            recipients,
            f"El ticket {t.code} está por vencer su SLA.",
            t,
        )


def _email_breach(t: Ticket, role_users=None):
    recipients = set(role_users or [])
    if t.assigned_to and t.assigned_to.is_active:
        recipients.add(t.assigned_to)
    if t.requester and getattr(t.requester, "is_active", False):
        recipients.add(t.requester)
    recipients = {u for u in recipients if getattr(u, "is_active", False)}
    emails = [getattr(u, "email", None) for u in recipients]
    emails = [email for email in emails if email]
    if emails:
        send_mail(
            subject=f"[{t.code}] SLA VENCIDO",
            message=f"El ticket {t.code} ({t.title}) ha vencido su SLA.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            fail_silently=True,
        )
    if recipients:
        _create_notifications(
            recipients,
            f"El ticket {t.code} ha vencido su SLA.",
            t,
        )

def apply_auto_assign(ticket: Ticket, actor=None) -> bool:
    qs = AutoAssignRule.objects.filter(is_active=True)
    rule = (qs.filter(category=ticket.category, area=ticket.area).first()
            or qs.filter(category=ticket.category, area__isnull=True).first()
            or qs.filter(category__isnull=True, area=ticket.area).first())
    if not rule:
        return False

    if ticket.assigned_to_id == rule.tech_id:
        return False

    prev = ticket.assigned_to
    ticket.assigned_to = rule.tech
    ticket.save(update_fields=["assigned_to", "updated_at"])

    TicketAssignment.objects.create(
        ticket=ticket, from_user=actor, to_user=rule.tech, reason="auto-assign"
    )
    AuditLog.objects.create(
        ticket=ticket, actor=actor, action="ASSIGN",
        meta={
            "from": prev.id if prev else None,
            "from_username": getattr(prev, "username", None) if prev else None,
            "to": rule.tech_id,
            "to_username": getattr(rule.tech, "username", None),
            "reason": "auto-assign",
        },
    )
    return True


def tickets_to_workbook(qs) -> Workbook:
    """Construye un workbook de Excel a partir de un queryset de tickets."""
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "Código",
            "Título",
            "Estado",
            "Categoría",
            "Prioridad",
            "Área",
            "Solicitante",
            "Asignado a",
            "Creado",
            "Resuelto",
            "Cerrado",
        ]
    )
    for t in qs:
        ws.append(
            [
                t.code,
                t.title,
                t.get_status_display(),
                getattr(t.category, "name", ""),
                getattr(t.priority, "name", ""),
                getattr(t.area, "name", ""),
                getattr(t.requester, "username", ""),
                getattr(t.assigned_to, "username", ""),
                timezone.localtime(t.created_at).strftime("%Y-%m-%d %H:%M"),
                timezone.localtime(t.resolved_at).strftime("%Y-%m-%d %H:%M") if t.resolved_at else "",
                timezone.localtime(t.closed_at).strftime("%Y-%m-%d %H:%M") if t.closed_at else "",
            ]
        )

    return wb