# reports/api.py
from collections import Counter
import csv
import calendar
from datetime import datetime, time, timedelta

from django.db.models import Count, Avg, DurationField, ExpressionWrapper, F
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncHour
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from helpdesk.permissions import AuthenticatedSafeMethodsOnlyForRequesters

from tickets.models import Ticket
from tickets.utils import (
    aggregate_top_subcategories,
    aggregate_area_by_subcategory,
    build_area_subcategory_heatmap,
)
from tickets.timezones import get_local_timezone
from accounts.roles import is_admin, is_tech
from django.utils import timezone


def parse_dt(s):
    # admite YYYY-MM-DD; si viene vacío, devuelve None
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def current_month_bounds():
    today = timezone.localdate()
    return today.replace(day=1), today


def resolve_range(raw_from, raw_to):
    dfrom = parse_dt(raw_from)
    dto = parse_dt(raw_to)
    start_month, today = current_month_bounds()

    if not raw_from and not raw_to:
        dfrom, dto = start_month, today
    else:
        if not dfrom and dto:
            dfrom = dto.replace(day=1)
        elif not dfrom:
            dfrom = start_month

        if not dto and dfrom:
            if dfrom.year == today.year and dfrom.month == today.month:
                dto = today
            else:
                last_day = calendar.monthrange(dfrom.year, dfrom.month)[1]
                dto = dfrom.replace(day=last_day)

    return dfrom, dto


def base_queryset(request):
    qs = Ticket.objects.select_related("category", "priority", "assigned_to")
    u = request.user

    # filtros por rol (ADMINISTRADOR ve todo; TECNICO solo asignados; SOLICITANTE propios)
    if is_admin(u):
        pass
    elif is_tech(u):
        qs = qs.filter(assigned_to=u)
    else:
        qs = qs.filter(requester=u)

    # filtros de fecha (rango en created_at)
    raw_from = request.query_params.get("from")
    raw_to = request.query_params.get("to")
    dfrom, dto = resolve_range(raw_from, raw_to)
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom)
    if dto:
        qs = qs.filter(created_at__date__lte=dto)

    cluster = (
        request.query_params.get("cluster_id")
        or request.query_params.get("cluster")
        or ""
    ).strip()
    if cluster:
        if cluster.isdigit():
            qs = qs.filter(cluster_id=int(cluster))
        else:
            cluster = ""

    category = (
        request.query_params.get("category_id")
        or request.query_params.get("category")
        or ""
    ).strip()
    if category:
        if category.isdigit():
            qs = qs.filter(category_id=int(category))
        else:
            qs = qs.filter(category__name__iexact=category)

    area = (
        request.query_params.get("area_id")
        or request.query_params.get("area")
        or ""
    ).strip()
    if area:
        if area.isdigit():
            qs = qs.filter(area_id=int(area))
        else:
            qs = qs.filter(area__name__iexact=area)
    return qs


class ReportSummaryView(APIView):
    permission_classes = [AuthenticatedSafeMethodsOnlyForRequesters]

    def get(self, request):
        qs = base_queryset(request)
        report_type = request.query_params.get("type")
        if report_type == "urgencia":
            qs = qs.filter(priority__name__icontains="urgencia")

        # --- by_status robusto (incluye estados con 0) ---
        status_list = list(qs.values_list("status", flat=True))
        cnt = Counter(status_list)
        status_map = dict(Ticket.STATUS_CHOICES)
        by_status = {status_map.get(key, key): cnt.get(key, 0) for key, _ in Ticket.STATUS_CHOICES}

        # por categoría
        by_category = [
            {"category": name, "count": c}
            for name, c in qs.values_list("category__name").annotate(c=Count("id"))
        ]

        # por prioridad
        by_priority = [
            {"priority": name, "count": c}
            for name, c in qs.values_list("priority__name").annotate(c=Count("id"))
        ]

        by_cluster = [
            {
                "cluster": cluster_id if cluster_id is not None else "Sin cluster",
                "count": c,
            }
            for cluster_id, c in qs.values_list("cluster_id").annotate(c=Count("id"))
        ]

        # por técnico asignado
        ass = qs.exclude(assigned_to__isnull=True)
        by_tech = [
            {"tech": username, "count": c}
            for username, c in ass.values_list("assigned_to__username").annotate(c=Count("id"))
        ]

        # TPR (horas promedio)
        dur = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        resolved = qs.exclude(resolved_at__isnull=True)
        avg_resolve = resolved.aggregate(avg=Avg(dur))["avg"]
        avg_resolve_hours = round(avg_resolve.total_seconds() / 3600, 2) if avg_resolve else None

        return Response({
            "counts": {
                "total": qs.count(),
                "by_status": by_status,
            },
            "by_category": by_category,
            "by_priority": by_priority,
            "by_cluster": by_cluster,
            "by_tech": by_tech,
            "avg_resolve_hours": avg_resolve_hours,
        })


class ReportExportView(APIView):
    permission_classes = [AuthenticatedSafeMethodsOnlyForRequesters]

    def get(self, request):
        qs = base_queryset(request)
        report_type = request.query_params.get("type")
        if report_type == "urgencia":
            qs = qs.filter(priority__name__icontains="urgencia")

        # --- Config CSV / Excel ---
        # Excel (es-CL/es-ES) suele esperar ; como separador
        sep = request.query_params.get("sep", ";")

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="tickets_export.csv"'

        # BOM para que Excel detecte UTF-8 y muestre bien tildes/ñ
        response.write("\ufeff")

        # Pista para Excel: usar este separador
        # (debe ser la primera línea del archivo)
        response.write(f"sep={sep}\r\n")

        writer = csv.writer(
            response,
            delimiter=sep,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\r\n",
        )

        # Encabezados
        writer.writerow([
            "id","code","title","status","requester","assigned_to",
            "category","priority","area","cluster_id","created_at","resolved_at","closed_at"
        ])

        # Filas
        for t in qs:
            writer.writerow([
                t.id,
                t.code,
                t.title,
                t.status,
                getattr(t.requester, "username", ""),
                getattr(t.assigned_to, "username", "") if t.assigned_to_id else "",
                getattr(t.category, "name", ""),
                getattr(t.priority, "key", ""),
                getattr(t.area, "name", "") if t.area_id else "",
                t.cluster_id or "",
                t.created_at.isoformat(timespec="seconds"),
                t.resolved_at.isoformat(timespec="seconds") if t.resolved_at else "",
                t.closed_at.isoformat(timespec="seconds") if t.closed_at else "",
            ])

        return response


class ReportHeatmapView(APIView):
    """Entrega una matriz día x hora para alimentar el mapa de calor."""

    permission_classes = [AuthenticatedSafeMethodsOnlyForRequesters]
    WEEKDAY_LABELS = [
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
        "Sábado",
        "Domingo",
    ]

    def get(self, request):
        qs = base_queryset(request)
        tz = get_local_timezone()

        aggregated = (
            qs.annotate(local_created=TruncHour("created_at", tzinfo=tz))
            .annotate(
                weekday=ExtractWeekDay("local_created"),
                hour=ExtractHour("local_created"),
            )
            .values("weekday", "hour")
            .annotate(count=Count("id"))
            .order_by("weekday", "hour")
        )

        hours = list(range(24))
        weekdays = list(self.WEEKDAY_LABELS)
        matrix = [[0 for _ in hours] for _ in weekdays]
        totals_by_weekday = [0 for _ in weekdays]
        totals_by_hour = [0 for _ in hours]
        max_value = 0

        for row in aggregated:
            weekday_raw = row.get("weekday")
            hour = row.get("hour")
            count = int(row.get("count") or 0)

            if weekday_raw is None or hour is None:
                continue

            weekday_index = (weekday_raw + 5) % 7  # django: 1=domingo → 6
            if weekday_index < 0 or weekday_index >= len(weekdays):
                continue
            if hour < 0 or hour >= len(hours):
                continue

            matrix[weekday_index][hour] = count
            totals_by_weekday[weekday_index] += count
            totals_by_hour[hour] += count
            if count > max_value:
                max_value = count

        total = sum(totals_by_weekday)

        return Response(
            {
                "hours": hours,
                "weekdays": weekdays,
                "matrix": matrix,
                "totals": {
                    "by_weekday": totals_by_weekday,
                    "by_hour": totals_by_hour,
                    "overall": total,
                },
                "max_value": max_value,
            }
        )


class ReportTopSubcategoriesView(APIView):
    """Devuelve el ranking de subcategorías del período."""

    permission_classes = [AuthenticatedSafeMethodsOnlyForRequesters]

    def get(self, request):
        qs = base_queryset(request)
        raw_from = request.query_params.get("from")
        raw_to = request.query_params.get("to")
        dfrom, _ = resolve_range(raw_from, raw_to)
        since = None
        if dfrom:
            since = timezone.make_aware(datetime.combine(dfrom, time.min))
        limit = request.query_params.get("limit")
        try:
            limit_value = int(limit) if limit is not None else 5
        except ValueError:
            limit_value = 5
        limit_value = max(1, min(limit_value, 20))

        results = aggregate_top_subcategories(qs, since=since, limit=limit_value)
        return Response(
            {
                "since": dfrom.isoformat() if dfrom else None,
                "results": results,
            }
        )


class ReportAreaBySubcategoryView(APIView):
    """Devuelve el cruce Área × Subcategoría ordenado por incidencias."""

    permission_classes = [AuthenticatedSafeMethodsOnlyForRequesters]

    def get(self, request):
        qs = base_queryset(request)
        raw_from = request.query_params.get("from")
        raw_to = request.query_params.get("to")
        dfrom, _ = resolve_range(raw_from, raw_to)
        since = None
        if dfrom:
            since = timezone.make_aware(datetime.combine(dfrom, time.min))

        limit = request.query_params.get("limit")
        try:
            limit_value = int(limit) if limit is not None else 10
        except ValueError:
            limit_value = 10
        limit_value = max(1, min(limit_value, 50))

        rows = aggregate_area_by_subcategory(qs, since=since, limit=limit_value)
        return Response(
            {
                "since": dfrom.isoformat() if dfrom else None,
                "results": rows,
            }
        )


class ReportAreaSubcategoryHeatmapView(APIView):
    """Construye un heatmap Área × Subcategoría."""

    permission_classes = [AuthenticatedSafeMethodsOnlyForRequesters]

    def get(self, request):
        qs = base_queryset(request)
        raw_from = request.query_params.get("from")
        raw_to = request.query_params.get("to")
        dfrom, _ = resolve_range(raw_from, raw_to)
        since = None
        if dfrom:
            since = timezone.make_aware(datetime.combine(dfrom, time.min))

        payload = build_area_subcategory_heatmap(qs, since=since)
        return Response(
            {
                "since": dfrom.isoformat() if dfrom else None,
                "cells": payload["cells"],
                "areas": payload["areas"],
                "subcategories": payload["subcategories"],
                "matrix": payload["matrix"],
            }
        )


