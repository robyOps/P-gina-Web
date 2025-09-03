# tickets/services.py
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import AuditLog, Ticket, AutoAssignRule, TicketAssignment
from django.db.models import Q
from openpyxl import Workbook

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
                    _email_breach(t)
                breached += 1
            continue

        # Aún no resuelto: breach
        if elapsed_h >= sla_hours and not _has_log(t, "SLA_BREACH"):
            if not dry_run:
                AuditLog.objects.create(ticket=t, actor=None, action="SLA_BREACH",
                                        meta={"due_at": due.isoformat(), "overdue_h": int((now - due).total_seconds() // 3600)})
                _email_breach(t)
            breached += 1
            continue

        # Warning
        if elapsed_h >= warn_th and not _has_log(t, "SLA_WARN"):
            if not dry_run:
                AuditLog.objects.create(ticket=t, actor=None, action="SLA_WARN",
                                        meta={"due_at": due.isoformat(), "remaining_h": int((due - now).total_seconds() // 3600)})
                _email_warn(t)
            warned += 1

    return {"warnings": warned, "breaches": breached}


def _email_warn(t: Ticket):
    to = [getattr(t.assigned_to, "email", None)]
    to = [x for x in to if x]
    if to:
        send_mail(
            subject=f"[{t.code}] SLA por vencer",
            message=f"El ticket {t.code} ({t.title}) está por vencer su SLA.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=to,
            fail_silently=True,
        )

def _email_breach(t: Ticket):
    to = [
        getattr(t.assigned_to, "email", None),
        getattr(t.requester, "email", None),
    ]
    to = [x for x in to if x]
    if to:
        send_mail(
            subject=f"[{t.code}] SLA VENCIDO",
            message=f"El ticket {t.code} ({t.title}) ha vencido su SLA.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=to,
            fail_silently=True,
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
        meta={"from": prev.id if prev else None, "to": rule.tech_id, "reason": "auto-assign"},
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