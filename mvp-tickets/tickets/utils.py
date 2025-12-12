"""
Propósito:
    Agrupar utilidades de sanitización y generación de métricas usadas en dashboards.
API pública:
    Funciones como ``sanitize_text``, ``aggregate_top_subcategories`` y los
    constructores de heatmaps.
Flujo de datos:
    QuerySets de ``Ticket`` → agregaciones/estructuras listas para la API.
Permisos:
    No aplica; se asume que la vista ya filtró el queryset según el rol.
Decisiones de diseño:
    Se evita usar ORM crudo; las agregaciones se realizan con ``annotate`` para
    mantener compatibilidad con múltiples motores de BD.
Riesgos:
    Cambios en nombres de campos pueden romper los heatmaps; actualizar pruebas en
    ``tickets/tests/test_analytics.py`` al modificar lógicas aquí.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time, timezone as dt_timezone
from typing import Sequence

from django.db.models import Count, QuerySet
from django.utils import timezone

from .timezones import get_local_timezone

from .models import Ticket


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


def _resolve_since(
    since: timezone.datetime | None,
    *,
    default_days: int = 30,
) -> timezone.datetime:
    """Normaliza el parámetro ``since`` para filtros comparables por fecha."""

    if since is None:
        return timezone.now() - timedelta(days=default_days)

    if timezone.is_naive(since):
        since = timezone.make_aware(since, dt_timezone.utc)

    if (
        since.hour == 0
        and since.minute == 0
        and since.second == 0
        and since.microsecond == 0
    ):
        utc_date = since.astimezone(dt_timezone.utc).date()
        return datetime.combine(utc_date, time.min, tzinfo=dt_timezone.utc)

    return since.astimezone(dt_timezone.utc)


def aggregate_top_subcategories(
    queryset: QuerySet[Ticket],
    *,
    since: timezone.datetime | None = None,
    limit: int = 5,
) -> list[dict[str, float | int | str]]:
    """Return the most common ticket subcategories within the period."""

    if limit <= 0:
        return []

    since = _resolve_since(since)
    filtered = queryset.filter(created_at__gte=since, subcategory__isnull=False)

    rows = (
        filtered.values("subcategory", "subcategory__name", "subcategory__category__name")
        .annotate(total=Count("id"))
        .order_by("-total", "subcategory__name")[:limit]
    )

    total = sum(row["total"] for row in rows)
    if total <= 0:
        return []

    aggregated: list[dict[str, float | int | str]] = []
    for row in rows:
        subtotal = int(row["total"])
        percentage = (subtotal / total) * 100 if total else 0.0
        aggregated.append(
            {
                "subcategory_id": row["subcategory"],
                "subcategory": row["subcategory__name"] or "Sin subcategoría",
                "category": row["subcategory__category__name"] or "Sin categoría",
                "total": subtotal,
                "percentage": round(percentage, 2),
            }
        )

    return aggregated


def aggregate_area_by_subcategory(
    queryset: QuerySet[Ticket],
    *,
    since: timezone.datetime | None = None,
    limit: int = 10,
) -> list[dict[str, object]]:
    """Return rows of area × subcategory counts ordered by volume."""

    since = _resolve_since(since)
    filtered = queryset.filter(
        created_at__gte=since, subcategory__isnull=False, area__isnull=False
    )

    rows = (
        filtered.values("area__name", "subcategory__name", "subcategory__category__name")
        .annotate(total=Count("id"))
        .order_by("-total", "area__name", "subcategory__name")[:limit]
    )

    return [
        {
            "area": row["area__name"] or "Sin área",
            "subcategory": row["subcategory__name"] or "Sin subcategoría",
            "category": row["subcategory__category__name"] or "Sin categoría",
            "total": int(row["total"]),
        }
        for row in rows
    ]


def build_area_subcategory_heatmap(
    queryset: QuerySet[Ticket],
    *,
    since: timezone.datetime | None = None,
) -> dict[str, object]:
    """Construye el payload del heatmap Área × Subcategoría.

    Parámetros:
        queryset: queryset previamente filtrado según rol/período.
        since: fecha mínima (aware) para limitar la ventana temporal.

    Retorna:
        Diccionario con llaves ``areas``, ``subcategories``, ``matrix`` y ``cells``
        listo para serializar en JSON.
    """

    since = _resolve_since(since)
    filtered = queryset.filter(
        created_at__gte=since, subcategory__isnull=False, area__isnull=False
    )

    rows = (
        filtered.values("area__name", "subcategory__name")
        .annotate(total=Count("id"))
        .order_by("area__name", "subcategory__name")
    )

    areas = sorted({row["area__name"] or "Sin área" for row in rows})
    subcategories = sorted({row["subcategory__name"] or "Sin subcategoría" for row in rows})

    area_index = {area: idx for idx, area in enumerate(areas)}
    subcategory_index = {sub: idx for idx, sub in enumerate(subcategories)}

    matrix = [[0 for _ in subcategories] for _ in areas]

    for row in rows:
        area = row["area__name"] or "Sin área"
        sub = row["subcategory__name"] or "Sin subcategoría"
        matrix[area_index[area]][subcategory_index[sub]] = int(row["total"])

    cells = []
    for area, area_pos in area_index.items():
        for sub, sub_pos in subcategory_index.items():
            cells.append(
                {
                    "area": area,
                    "subcategory": sub,
                    "count": matrix[area_pos][sub_pos],
                }
            )

    return {
        "areas": areas,
        "subcategories": subcategories,
        "matrix": matrix,
        "cells": cells,
    }


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
    date_from: date | None = None,
    date_to: date | None = None,
    auto_range: bool = True,
) -> HeatmapPayload:
    """Genera la matriz Semana × Hora para el heatmap principal.

    Parámetros:
        queryset: tickets ya filtrados por permisos/fecha.
        since: fecha mínima; si es ``None`` y ``auto_range`` es ``True`` se toma
            un rango de 14 días.
        auto_range: controla si se aplica el rango dinámico por defecto.

    Retorna:
        ``HeatmapPayload`` con totales por hora y día además de la matriz normalizada.
    """

    if auto_range and since is None and date_from is None and date_to is None:
        since = timezone.now() - timedelta(days=13)
    tz = get_local_timezone()

    filtered = queryset
    if since is not None:
        filtered = filtered.filter(created_at__gte=since)

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

    created_values = (
        filtered.order_by("created_at")
        .values_list("created_at", flat=True)
        .iterator()
    )

    for created_at in created_values:
        if not created_at:
            continue

        local_created = created_at
        if timezone.is_naive(local_created):
            local_created = timezone.make_aware(local_created, timezone.utc)
        local_created = timezone.localtime(local_created, tz)

        local_date = local_created.date()
        if date_from and local_date < date_from:
            continue
        if date_to and local_date > date_to:
            continue

        weekday_index = local_created.weekday()
        hour = local_created.hour

        if weekday_index < 0 or weekday_index >= len(weekdays):
            continue

        matrix[weekday_index][hour] += 1
        totals_by_weekday[weekday_index] += 1
        totals_by_hour[hour] += 1
        if matrix[weekday_index][hour] > max_value:
            max_value = matrix[weekday_index][hour]

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


