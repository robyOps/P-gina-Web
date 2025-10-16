"""Servicios auxiliares del módulo de tickets."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Dict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from accounts.roles import ROLE_ADMIN, ROLE_TECH

from .models import (
    AuditLog,
    AutoAssignRule,
    Notification,
    Ticket,
    TicketAssignment,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Utilidades privadas
# ---------------------------------------------------------------------------

def _has_log(ticket: Ticket, action: str) -> bool:
    """Revisa si ya existe un registro de auditoría para evitar duplicados."""

    return AuditLog.objects.filter(ticket=ticket, action=action).exists()


def _active_users_from(users: Iterable) -> set:
    """Filtra elementos no usuarios y aquellos inactivos."""

    return {
        user
        for user in users
        if getattr(user, "is_active", False)
    }


def _collect_recipients(ticket: Ticket, base_users: Iterable) -> set:
    """Agrupa los usuarios que deben ser notificados por SLA."""

    recipients = _active_users_from(base_users)

    if ticket.assigned_to and ticket.assigned_to.is_active:
        recipients.add(ticket.assigned_to)
    if ticket.requester and getattr(ticket.requester, "is_active", False):
        recipients.add(ticket.requester)

    return _active_users_from(recipients)


def _notify_users(ticket: Ticket, message: str, recipients: set) -> None:
    """Envía emails y notificaciones in-app a los destinatarios dados."""

    emails = [getattr(user, "email", None) for user in recipients]
    email_list = [email for email in emails if email]

    if email_list:
        send_mail(
            subject=message.split(".")[0],
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=email_list,
            fail_silently=True,
        )

    if recipients:
        link = reverse("ticket_detail", args=[ticket.pk])
        notifications = [
            Notification(user=user, message=message, url=link) for user in recipients
        ]
        Notification.objects.bulk_create(notifications)


def _email_warn(ticket: Ticket, role_users: Iterable) -> None:
    """Comunica un estado de advertencia de SLA."""

    recipients = _collect_recipients(ticket, role_users)
    if recipients:
        _notify_users(
            ticket,
            f"El ticket {ticket.code} ({ticket.title}) está por vencer su SLA.",
            recipients,
        )


def _email_breach(ticket: Ticket, role_users: Iterable | None = None) -> None:
    """Comunica un estado de incumplimiento de SLA."""

    recipients = _collect_recipients(ticket, role_users or [])
    if recipients:
        _notify_users(
            ticket,
            f"El ticket {ticket.code} ({ticket.title}) ha vencido su SLA.",
            recipients,
        )


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def run_sla_check(*, warn_ratio: float = 0.8, dry_run: bool = False) -> Dict[str, int]:
    """Evalúa el cumplimiento de SLA y dispara alertas o incumplimientos."""

    now = timezone.now()
    qs = (
        Ticket.objects.select_related("priority", "requester", "assigned_to")
        .filter(status__in=[Ticket.OPEN, Ticket.IN_PROGRESS])
        .only(
            "id",
            "code",
            "title",
            "status",
            "priority__sla_hours",
            "created_at",
            "resolved_at",
            "due_at",
        )
    )

    warned = breached = 0

    role_users = []
    if not dry_run:
        role_users = list(
            User.objects.filter(
                is_active=True, groups__name__in=[ROLE_TECH, ROLE_ADMIN]
            ).distinct()
        )

    for ticket in qs:
        sla_hours = ticket.sla_hours_value
        due = ticket.due_at
        elapsed_h = (now - ticket.created_at).total_seconds() / 3600.0
        warn_threshold = sla_hours * warn_ratio

        # Tickets resueltos: registrar BREACH solo si ocurrió después del SLA.
        if ticket.resolved_at:
            if ticket.resolved_at > due and not _has_log(ticket, "SLA_BREACH"):
                if not dry_run:
                    AuditLog.objects.create(
                        ticket=ticket,
                        actor=None,
                        action="SLA_BREACH",
                        meta={
                            "due_at": due.isoformat(),
                            "resolved_at": ticket.resolved_at.isoformat(),
                        },
                    )
                    _email_breach(ticket, role_users)
                breached += 1
            continue

        # Tickets abiertos: evaluar incumplimiento.
        if elapsed_h >= sla_hours and not _has_log(ticket, "SLA_BREACH"):
            if not dry_run:
                AuditLog.objects.create(
                    ticket=ticket,
                    actor=None,
                    action="SLA_BREACH",
                    meta={
                        "due_at": due.isoformat(),
                        "overdue_h": int((now - due).total_seconds() // 3600),
                    },
                )
                _email_breach(ticket, role_users)
            breached += 1
            continue

        # Tickets dentro del umbral: enviar advertencia cuando corresponda.
        if elapsed_h >= warn_threshold and not _has_log(ticket, "SLA_WARN"):
            if not dry_run:
                AuditLog.objects.create(
                    ticket=ticket,
                    actor=None,
                    action="SLA_WARN",
                    meta={
                        "due_at": due.isoformat(),
                        "remaining_h": int((due - now).total_seconds() // 3600),
                    },
                )
                _email_warn(ticket, role_users)
            warned += 1

    return {"warnings": warned, "breaches": breached}


def send_daily_expiring_ticket_summary(*, within_hours: int = 24, dry_run: bool = False) -> Dict[str, int]:
    """Envía un resumen diario de tickets cuyo SLA vencerá pronto."""

    now = timezone.now()
    window_end = now + timedelta(hours=within_hours)

    qs = Ticket.objects.select_related("priority", "assigned_to", "requester").filter(
        status__in=[Ticket.OPEN, Ticket.IN_PROGRESS]
    )

    expiring = []
    for ticket in qs:
        due = ticket.due_at
        if due and now <= due <= window_end:
            expiring.append((ticket, due))

    expiring.sort(key=lambda item: item[1])

    role_users = _active_users_from(
        User.objects.filter(is_active=True, groups__name__in=[ROLE_TECH, ROLE_ADMIN]).distinct()
    )

    summary = {"tickets": len(expiring), "recipients": len(role_users)}

    if not expiring or not role_users:
        return summary

    if dry_run:
        return summary

    subject = "[Helpdesk] Tickets por vencer"
    link = reverse("reports_dashboard")

    lines = [
        "Hola,",
        "",
        f"Estos {('ticket' if len(expiring) == 1 else 'tickets')} vencerán en las próximas {within_hours} horas:",
        "",
    ]

    for ticket, due in expiring:
        due_local = timezone.localtime(due)
        assigned = getattr(ticket.assigned_to, "username", "Sin asignar") or "Sin asignar"
        lines.append(
            f"- {ticket.code} · {ticket.title} (vence {due_local.strftime('%d/%m %H:%M')} · asignado a {assigned})"
        )

    lines.extend(
        [
            "",
            "Puedes revisar el detalle completo en el panel de reportes:",
            link,
        ]
    )

    body = "\n".join(lines)

    emails = [getattr(user, "email", None) for user in role_users]
    email_list = [email for email in emails if email]
    if email_list:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=email_list,
            fail_silently=True,
        )

    notif_message = (
        f"{len(expiring)} ticket{' está' if len(expiring) == 1 else 's están'} por vencer en las próximas {within_hours} horas."
    )
    notifications = [
        Notification(user=user, message=notif_message, url=link) for user in role_users
    ]
    Notification.objects.bulk_create(notifications)

    return summary


def apply_auto_assign(ticket: Ticket, actor=None) -> bool:
    """Aplica la regla de auto-asignación que coincida con el ticket."""

    qs = AutoAssignRule.objects.filter(is_active=True)
    rule = (
        qs.filter(category=ticket.category, area=ticket.area).first()
        or qs.filter(category=ticket.category, area__isnull=True).first()
        or qs.filter(category__isnull=True, area=ticket.area).first()
    )
    if not rule or ticket.assigned_to_id == rule.tech_id:
        return False

    previous_assignee = ticket.assigned_to
    ticket.assigned_to = rule.tech
    ticket.save(update_fields=["assigned_to", "updated_at"])

    TicketAssignment.objects.create(
        ticket=ticket,
        from_user=actor,
        to_user=rule.tech,
        reason="auto-assign",
    )
    AuditLog.objects.create(
        ticket=ticket,
        actor=actor,
        action="ASSIGN",
        meta={
            "from": getattr(previous_assignee, "id", None),
            "from_username": getattr(previous_assignee, "username", None),
            "to": rule.tech_id,
            "to_username": getattr(rule.tech, "username", None),
            "reason": "auto-assign",
        },
    )
    return True


def tickets_to_workbook(qs) -> Workbook:
    """Construye un archivo Excel a partir de un queryset de tickets."""

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

    for ticket in qs:
        ws.append(
            [
                ticket.code,
                ticket.title,
                ticket.get_status_display(),
                getattr(ticket.category, "name", ""),
                getattr(ticket.priority, "name", ""),
                getattr(ticket.area, "name", ""),
                getattr(ticket.requester, "username", ""),
                getattr(ticket.assigned_to, "username", ""),
                timezone.localtime(ticket.created_at).strftime("%Y-%m-%d %H:%M"),
                timezone.localtime(ticket.resolved_at).strftime("%Y-%m-%d %H:%M")
                if ticket.resolved_at
                else "",
                timezone.localtime(ticket.closed_at).strftime("%Y-%m-%d %H:%M")
                if ticket.closed_at
                else "",
            ]
        )

    return wb
