"""Servicios reutilizables para lógica de criticidad y notificaciones asociadas."""

from __future__ import annotations

from typing import Iterable, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import BooleanField, Case, IntegerField, Value, When
from django.db.models.functions import Coalesce
from django.urls import reverse

from accounts.roles import ROLE_ADMIN, ROLE_TECH
from .models import Notification

User = get_user_model()


def _is_actor_critical(actor) -> bool:
    return bool(actor and getattr(actor, "is_critical_actor", False))


def _is_ticket_area_critical(ticket) -> bool:
    try:
        return bool(ticket.area and getattr(ticket.area, "is_critical", False))
    except Exception:
        return False


def is_ticket_critical(ticket, actor) -> Tuple[bool, list[str]]:
    reasons: list[str] = []
    if _is_actor_critical(actor):
        reasons.append("usuario")
    if _is_ticket_area_critical(ticket):
        reasons.append("área")
    return bool(reasons), reasons


def critical_score_for(ticket, actor) -> int:
    score = 0
    if _is_actor_critical(actor):
        score += getattr(settings, "CRITICAL_USER_WEIGHT", 2)
    if _is_ticket_area_critical(ticket):
        score += getattr(settings, "CRITICAL_AREA_WEIGHT", 1)
    return score


def annotate_critical_score(queryset, actor=None):
    user_weight = getattr(settings, "CRITICAL_USER_WEIGHT", 2)
    area_weight = getattr(settings, "CRITICAL_AREA_WEIGHT", 1)
    actor_is_critical = _is_actor_critical(actor)

    return queryset.annotate(
        critical_user=Value(actor_is_critical, output_field=BooleanField()),
        critical_area=Case(
            When(area__is_critical=True, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        critical_score=Coalesce(
            Value(user_weight if actor_is_critical else 0, output_field=IntegerField()),
            Value(0, output_field=IntegerField()),
        )
        + Case(
            When(area__is_critical=True, then=Value(area_weight)),
            default=Value(0),
            output_field=IntegerField(),
        ),
    )


def _recipients_for_critical_events() -> Iterable[User]:
    groups = list(Group.objects.filter(name__in=[ROLE_TECH, ROLE_ADMIN]))
    if not groups:
        return []
    return (
        User.objects.filter(is_active=True, groups__in=groups)
        .distinct()
        .only("id", "username")
    )


def notify_if_critical(ticket, actor, action_desc: str) -> None:
    score = critical_score_for(ticket, actor)
    if score <= 0:
        return

    critical, reasons = is_ticket_critical(ticket, actor)
    if not critical:
        return

    recipients = list(_recipients_for_critical_events())
    if not recipients:
        return

    reason_label = " y ".join(reasons)
    priority_label = getattr(getattr(ticket, "priority", None), "name", "") or "sin prioridad"
    status_label = getattr(ticket, "status", "") or ""
    message = (
        f"Atención crítica ({reason_label}): ticket {ticket.code} {action_desc}. "
        f"Estado {status_label}, prioridad {priority_label}."
    )
    try:
        url = reverse("ticket_detail", args=[ticket.pk])
    except Exception:
        url = ""

    Notification.objects.bulk_create(
        [Notification(user=user, message=message, url=url) for user in recipients]
    )
