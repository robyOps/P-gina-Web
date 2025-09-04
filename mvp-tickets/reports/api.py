# reports/api.py
from datetime import datetime
from collections import Counter
import csv

from django.db.models import Count, Avg, DurationField, ExpressionWrapper, F
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

from tickets.models import Ticket
from accounts.roles import is_admin, is_tech


def parse_dt(s):
    # admite YYYY-MM-DD; si viene vacío, devuelve None
    if not s:
        return None
    return datetime.fromisoformat(s)


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
    dfrom = parse_dt(request.query_params.get("from"))
    dto = parse_dt(request.query_params.get("to"))
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom.date())
    if dto:
        qs = qs.filter(created_at__date__lte=dto.date())
    return qs


class ReportSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
            "by_tech": by_tech,
            "avg_resolve_hours": avg_resolve_hours,
        })


class ReportExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
            "category","priority","area","created_at","resolved_at","closed_at"
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
                t.created_at.isoformat(timespec="seconds"),
                t.resolved_at.isoformat(timespec="seconds") if t.resolved_at else "",
                t.closed_at.isoformat(timespec="seconds") if t.closed_at else "",
            ])

        return response


