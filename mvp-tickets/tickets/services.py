"""Servicios auxiliares del módulo de tickets."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable as IterableType, List, Tuple
from decimal import Decimal
import re
import time

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
    TicketLabel,
    TicketLabelSuggestion,
)

User = get_user_model()


@dataclass(slots=True)
class TicketAlertSnapshot:
    """Representa el estado de alerta SLA de un ticket."""

    ticket: Ticket
    severity: str
    due_at: datetime
    remaining_hours: float
    elapsed_hours: float
    threshold_hours: float


# Parámetros por defecto para sugerencias de etiquetas
DEFAULT_LABEL_SUGGESTION_THRESHOLD = 0.35

# Palabras clave y etiquetas asociadas
KEYWORD_LABELS = {
    "error": "Error",
    "bug": "Bug",
    "fallo": "Error",
    "caido": "Caída de servicio",
    "caída": "Caída de servicio",
    "lento": "Rendimiento",
    "demora": "Rendimiento",
    "factura": "Facturación",
    "facturación": "Facturación",
    "pago": "Pagos",
    "pagos": "Pagos",
    "correo": "Correo",
    "email": "Correo",
    "mail": "Correo",
    "vpn": "VPN",
    "acceso": "Acceso",
    "login": "Acceso",
    "contraseña": "Credenciales",
    "password": "Credenciales",
    "clave": "Credenciales",
    "bloqueado": "Bloqueo de usuario",
    "bloqueada": "Bloqueo de usuario",
    "actualización": "Actualización",
    "actualizar": "Actualización",
    "instalación": "Instalación",
    "instalar": "Instalación",
}


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
            "Subcategoría",
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
                getattr(ticket.subcategory, "name", ""),
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


# ---------------------------------------------------------------------------
# Etiquetas sugeridas
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    pattern = re.compile(r"[\wáéíóúñüÁÉÍÓÚÑÜ]+", re.UNICODE)
    return [chunk.lower() for chunk in pattern.findall(text or "")]


def get_label_suggestion_threshold() -> float:
    """Obtiene el umbral configurado para sugerencias (fallback al default)."""

    value = getattr(settings, "TICKET_LABEL_SUGGESTION_THRESHOLD", DEFAULT_LABEL_SUGGESTION_THRESHOLD)
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return DEFAULT_LABEL_SUGGESTION_THRESHOLD


def generate_label_candidates(ticket: Ticket) -> List[Tuple[str, float]]:
    """Calcula candidatos de etiquetas en base a título y descripción."""

    text = f"{ticket.title}\n{ticket.description}"
    tokens = _tokenize(text)
    if not tokens:
        return []

    counts: Counter[str] = Counter()
    for token in tokens:
        label = KEYWORD_LABELS.get(token)
        if label:
            counts[label] += 1

    # Bonus según categoría/área conocida
    if ticket.category_id:
        counts[f"Categoría: {ticket.category.name}"] += 1.5
    if ticket.area_id:
        counts[f"Área: {ticket.area.name}"] += 1.2

    total_tokens = len(tokens)
    suggestions: List[Tuple[str, float]] = []
    for label, weight in counts.items():
        raw_score = (weight / total_tokens) * 3
        clamped = max(0.05, min(raw_score, 1.0))
        # Redondeamos a dos decimales para guardar en DecimalField
        score = round(clamped + 0.1, 2)
        suggestions.append((label, float(score)))

    suggestions.sort(key=lambda item: item[1], reverse=True)
    return suggestions


def recompute_ticket_label_suggestions(
    ticket: Ticket,
    *,
    threshold: float | None = None,
) -> Dict[str, int | float]:
    """Recalcula sugerencias para un ticket respetando el umbral indicado."""

    threshold_value = get_label_suggestion_threshold() if threshold is None else max(0.0, min(float(threshold), 1.0))

    candidates = generate_label_candidates(ticket)
    seen: set[str] = set()
    created = updated = removed = 0

    existing: Dict[str, TicketLabelSuggestion] = {
        suggestion.label.lower(): suggestion
        for suggestion in ticket.label_suggestions.all()
    }

    for label, score in candidates:
        if score < threshold_value:
            continue
        key = label.lower()
        seen.add(key)
        suggestion = existing.get(key)
        decimal_score = Decimal(f"{score:.2f}")
        if suggestion:
            if suggestion.score != decimal_score:
                suggestion.score = decimal_score
                suggestion.save(update_fields=["score", "updated_at"])
                updated += 1
            continue
        TicketLabelSuggestion.objects.create(ticket=ticket, label=label, score=decimal_score)
        created += 1

    for suggestion in ticket.label_suggestions.filter(is_accepted=False):
        if suggestion.label.lower() not in seen:
            suggestion.delete()
            removed += 1

    total = ticket.label_suggestions.count()
    return {
        "created": created,
        "updated": updated,
        "removed": removed,
        "total": total,
        "threshold": threshold_value,
    }


def bulk_recompute_ticket_label_suggestions(
    *,
    queryset: IterableType[Ticket] | None = None,
    threshold: float | None = None,
    chunk_size: int = 200,
) -> Dict[str, float | int]:
    """Recalcula sugerencias en lote registrando métricas básicas."""

    if chunk_size <= 0:
        chunk_size = 200

    qs = queryset or Ticket.objects.all()
    if hasattr(qs, "order_by"):
        qs = qs.order_by("id")

    detected = qs.count() if hasattr(qs, "count") else 0
    started_at = timezone.now()
    start = time.perf_counter()

    processed = created = updated = removed = 0

    iterator = qs.iterator(chunk_size=chunk_size) if hasattr(qs, "iterator") else qs

    for ticket in iterator:
        processed += 1
        result = recompute_ticket_label_suggestions(ticket, threshold=threshold)
        created += int(result.get("created", 0))
        updated += int(result.get("updated", 0))
        removed += int(result.get("removed", 0))

    duration = round(time.perf_counter() - start, 4)

    finished_at = timezone.now()

    return {
        "tickets_detected": detected,
        "tickets_processed": processed,
        "suggestions_created": created,
        "suggestions_updated": updated,
        "suggestions_removed": removed,
        "threshold": (
            get_label_suggestion_threshold()
            if threshold is None
            else max(0.0, min(float(threshold), 1.0))
        ),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
    }


def accept_ticket_label_suggestion(
    suggestion: TicketLabelSuggestion,
    *,
    actor,
) -> TicketLabel:
    """Acepta una sugerencia y crea la etiqueta confirmada."""

    suggestion.mark_accepted(user=actor)
    label, _ = TicketLabel.objects.get_or_create(
        ticket=suggestion.ticket,
        name=suggestion.label,
        defaults={"created_by": actor},
    )
    if label.created_by is None and actor:
        label.created_by = actor
        label.save(update_fields=["created_by"])

    AuditLog.objects.create(
        ticket=suggestion.ticket,
        actor=actor,
        action="UPDATE",
        meta={
            "labels": [label.name],
            "source": "label_suggestion",
        },
    )

    return label


def collect_ticket_alerts(
    queryset: IterableType[Ticket] | None = None,
    *,
    warn_ratio: float = 0.8,
    now: datetime | None = None,
) -> List[TicketAlertSnapshot]:
    """Devuelve alertas SLA activas para el conjunto de tickets dado."""

    qs = queryset or Ticket.objects.all()
    warn_ratio = max(0.0, min(float(warn_ratio or 0.0), 1.0))
    now = now or timezone.now()

    snapshots: List[TicketAlertSnapshot] = []

    iterator = qs.iterator(chunk_size=200) if hasattr(qs, "iterator") else qs

    for ticket in iterator:
        sla_hours = ticket.sla_hours_value
        threshold_hours = sla_hours * warn_ratio
        due_at = ticket.due_at
        elapsed_hours = max(0.0, (now - ticket.created_at).total_seconds() / 3600.0)

        severity: str | None = None

        if ticket.resolved_at:
            if ticket.resolved_at > due_at:
                severity = "breach"
        else:
            if now >= due_at:
                severity = "breach"
            elif elapsed_hours >= threshold_hours:
                severity = "warning"

        if not severity:
            continue

        remaining_hours = (due_at - now).total_seconds() / 3600.0

        snapshots.append(
            TicketAlertSnapshot(
                ticket=ticket,
                severity=severity,
                due_at=due_at,
                remaining_hours=remaining_hours,
                elapsed_hours=elapsed_hours,
                threshold_hours=threshold_hours,
            )
        )

    return snapshots
