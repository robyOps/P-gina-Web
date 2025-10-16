"""Utilities focused on data hygiene and analytics helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from django.db.models import Count, QuerySet
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncHour
from django.utils import timezone

from .models import Ticket, TicketLabel
from .services import TicketAlertSnapshot, collect_ticket_alerts


_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_text(value: str | None) -> str:
    """Remove HTML tags and compact whitespace in user provided content."""

    if value is None:
        return ""

    # Django's ``strip_tags`` lives in ``django.utils.html``; importing lazily avoids
    # circular imports for consumers that do not require sanitisation.
    from django.utils.html import strip_tags

    cleaned = strip_tags(str(value))
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def aggregate_top_subcategories(
    queryset: QuerySet[Ticket],
    *,
    since: timezone.datetime | None = None,
    limit: int = 5,
) -> list[dict[str, float | int | str]]:
    """Return the most used ticket labels (used as subcategories) in the window.

    The aggregation intentionally works with labels only which prevents exposing
    Personally Identifiable Information (PII) in analytical widgets.
    """

    if limit <= 0:
        return []

    since = since or timezone.now() - timedelta(days=30)
    filtered_ids = queryset.filter(created_at__gte=since).values("pk")

    label_rows = (
        TicketLabel.objects.filter(ticket__in=filtered_ids)
        .values("name")
        .annotate(total=Count("id"))
        .order_by("-total", "name")[:limit]
    )

    total = sum(row["total"] for row in label_rows)
    if total <= 0:
        return []

    aggregated: list[dict[str, float | int | str]] = []
    for row in label_rows:
        name = row["name"] or "Sin etiqueta"
        subtotal = int(row["total"])
        percentage = (subtotal / total) * 100 if total else 0.0
        aggregated.append(
            {
                "name": name,
                "total": subtotal,
                "percentage": round(percentage, 2),
            }
        )

    return aggregated


@dataclass(slots=True)
class HeatmapPayload:
    weekdays: Sequence[str]
    hours: Sequence[int]
    matrix: Sequence[Sequence[int]]
    normalized: Sequence[Sequence[float]]
    rows: Sequence[dict[str, object]]
    totals_by_weekday: Sequence[int]
    totals_by_hour: Sequence[int]
    overall_total: int
    max_value: int


def build_ticket_heatmap(
    queryset: QuerySet[Ticket],
    *,
    since: timezone.datetime | None = None,
) -> HeatmapPayload:
    """Produce a week-day/hour matrix with ticket counts."""

    since = since or timezone.now() - timedelta(days=13)
    tz = timezone.get_current_timezone()

    filtered = queryset.filter(created_at__gte=since)
    aggregated = (
        filtered.annotate(local_created=TruncHour("created_at", tzinfo=tz))
        .annotate(
            weekday=ExtractWeekDay("local_created"),
            hour=ExtractHour("local_created"),
        )
        .values("weekday", "hour")
        .annotate(count=Count("id"))
        .order_by("weekday", "hour")
    )

    hours = list(range(24))
    weekdays = [
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
        "Sábado",
        "Domingo",
    ]
    matrix = [[0 for _ in hours] for _ in weekdays]
    normalized = [[0.0 for _ in hours] for _ in weekdays]
    totals_by_weekday = [0 for _ in weekdays]
    totals_by_hour = [0 for _ in hours]
    max_value = 0

    for row in aggregated:
        weekday_raw = row.get("weekday")
        hour = row.get("hour")
        count = int(row.get("count") or 0)

        if weekday_raw is None or hour is None:
            continue

        # Django: 1=domingo…7=sábado → shift to Monday based index
        weekday_index = (int(weekday_raw) + 5) % 7
        if weekday_index < 0 or weekday_index >= len(weekdays):
            continue
        if hour < 0 or hour >= len(hours):
            continue

        matrix[weekday_index][hour] = count
        totals_by_weekday[weekday_index] += count
        totals_by_hour[hour] += count
        max_value = max(max_value, count)

    overall_total = sum(totals_by_weekday)
    if max_value > 0:
        for y, row in enumerate(matrix):
            for x, value in enumerate(row):
                normalized[y][x] = value / max_value if max_value else 0.0

    row_payload: list[dict[str, object]] = []
    for idx, weekday in enumerate(weekdays):
        cells = []
        for hour_idx, hour in enumerate(hours):
            cells.append(
                {
                    "hour": hour,
                    "count": matrix[idx][hour_idx],
                    "intensity": normalized[idx][hour_idx],
                }
            )
        row_payload.append({"weekday": weekday, "cells": cells})

    return HeatmapPayload(
        weekdays=weekdays,
        hours=hours,
        matrix=matrix,
        normalized=normalized,
        rows=row_payload,
        totals_by_weekday=totals_by_weekday,
        totals_by_hour=totals_by_hour,
        overall_total=overall_total,
        max_value=max_value,
    )


def recent_ticket_alerts(
    queryset: QuerySet[Ticket],
    *,
    warn_ratio: float = 0.8,
    limit: int = 5,
) -> dict[str, object]:
    """Summarise SLA alerts limited to the user's visible tickets."""

    base = queryset.filter(status__in=[Ticket.OPEN, Ticket.IN_PROGRESS])
    base = base.select_related("priority", "assigned_to")

    snapshots = collect_ticket_alerts(base, warn_ratio=warn_ratio)

    if not snapshots:
        return {"items": [], "summary": {"warnings": 0, "breaches": 0}}

    total_warnings = sum(1 for snap in snapshots if snap.severity == "warning")
    total_breaches = sum(1 for snap in snapshots if snap.severity == "breach")

    sorted_snaps = sorted(
        snapshots,
        key=lambda snap: (
            0 if snap.severity == "breach" else 1,
            snap.remaining_hours,
        ),
    )

    limited: Sequence[TicketAlertSnapshot] = sorted_snaps[: max(1, limit)]

    items: list[dict[str, object]] = []
    for snap in limited:
        ticket = snap.ticket
        items.append(
            {
                "id": ticket.id,
                "code": ticket.code,
                "title": ticket.title,
                "severity": snap.severity,
                "due_at": timezone.localtime(snap.due_at),
                "remaining_hours": snap.remaining_hours,
                "assigned_to": getattr(ticket.assigned_to, "username", None),
            }
        )

    return {
        "items": items,
        "summary": {"warnings": total_warnings, "breaches": total_breaches},
    }

