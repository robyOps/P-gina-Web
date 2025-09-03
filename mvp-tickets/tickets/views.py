# tickets/views.py
from __future__ import annotations

# --- Django core ---
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.http import (
    HttpResponseForbidden,
    HttpResponseBadRequest,
    HttpResponse,
)

from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.template.loader import get_template
from django.utils import timezone
from django.utils.timezone import localtime


from django.shortcuts import render
from .forms import AutoAssignRuleForm
from .models import AutoAssignRule

# --- Stdlib ---
from datetime import datetime
import uuid
from io import BytesIO
from urllib.parse import urlencode

# --- Third-party ---
from xhtml2pdf import pisa

# --- Auth / models ---
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from django.db.models import Count, Avg, DurationField, ExpressionWrapper, F

# --- App local ---
from .forms import TicketCreateForm
from .models import (
    Ticket,
    TicketComment,
    TicketAttachment,
    TicketAssignment,
    AuditLog,
)


from .api import is_admin, is_tech  # helpers de rol (reutilizamos)
from .services import run_sla_check, apply_auto_assign, tickets_to_workbook
from .validators import validate_upload, UploadValidationError

User = get_user_model()


# ----------------- helpers -----------------
def allowed_transitions_for(ticket: Ticket, user) -> list[str]:
    """Transiciones permitidas según estado actual y rol."""
    allowed = {
        Ticket.OPEN: {Ticket.IN_PROGRESS},
        Ticket.IN_PROGRESS: {Ticket.RESOLVED, Ticket.OPEN},
        Ticket.RESOLVED: {Ticket.CLOSED, Ticket.IN_PROGRESS},
        Ticket.CLOSED: set(),
    }
    if is_admin(user) or (is_tech(user) and ticket.assigned_to_id == user.id):
        return list(allowed.get(ticket.status, set()))
    return []


def _parse_date_param(s: str | None):
    """YYYY-MM-DD -> date | None (ignora formatos inválidos)."""
    try:
        return datetime.fromisoformat(s).date() if s else None
    except Exception:
        return None


# ----------------- vistas UI -----------------
@login_required
def tickets_home(request):
    """
    Listado según rol con filtros + búsqueda + paginación.
    Query params:
      - q: busca en code, title, description
      - status, category, priority: filtros exactos
      - page, page_size: paginación (por defecto 20)
    """
    u = request.user
    base_qs = Ticket.objects.select_related("category", "priority", "assigned_to")

    other_qs = None
    if is_admin(u):
        qs = base_qs
    elif is_tech(u):
        qs = base_qs.filter(assigned_to=u)
        other_qs = base_qs.filter(assigned_to__groups__name="TECH").exclude(assigned_to=u)
    else:
        qs = base_qs.filter(requester=u)

    # Filtros
    status   = (request.GET.get("status") or "").strip()
    category = (request.GET.get("category") or "").strip()
    priority = (request.GET.get("priority") or "").strip()

    # Por defecto ocultar CLOSED si no hay filtro de estado
    if not status:
        qs = qs.exclude(status=Ticket.CLOSED)
        if other_qs is not None:
            other_qs = other_qs.exclude(status=Ticket.CLOSED)

    if status:
        qs = qs.filter(status=status)
        if other_qs is not None:
            other_qs = other_qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)
        if other_qs is not None:
            other_qs = other_qs.filter(category_id=category)
    if priority:
        qs = qs.filter(priority_id=priority)
        if other_qs is not None:
            other_qs = other_qs.filter(priority_id=priority)

    # Búsqueda
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) |
            Q(title__icontains=q) |
            Q(description__icontains=q)
        )
        if other_qs is not None:
            other_qs = other_qs.filter(
                Q(code__icontains=q)
                | Q(title__icontains=q)
                | Q(description__icontains=q)
            )

    # Ordenamiento
    sort = (request.GET.get("sort") or "").strip()
    allowed_sorts = {
        "code",
        "title",
        "status",
        "category__name",
        "priority__name",
        "assigned_to__username",
        "created_at",
    }
    sort_key = sort.lstrip("-")
    if sort_key in allowed_sorts:
        qs = qs.order_by(sort)
        if other_qs is not None:
            other_qs = other_qs.order_by(sort)
    else:
        qs = qs.order_by("-created_at")
        if other_qs is not None:
            other_qs = other_qs.order_by("-created_at")

    # Paginación
    try:
        page_size = int(request.GET.get("page_size", 20))
    except ValueError:
        page_size = 20
    page_size = max(5, min(page_size, 100))  # clamp 5..100

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))
    other_tickets = list(other_qs[:50]) if other_qs is not None else []

    # Para el combo de estados
    statuses = [key for key, _ in Ticket.STATUS_CHOICES]

    # Para preservar filtros en paginación (opcional, usado en template)
    qdict = request.GET.copy()
    qdict.pop("page", None)
    qs_no_page = qdict.urlencode()
    qs_no_page = f"&{qs_no_page}" if qs_no_page else ""

    qdict_no_sort = qdict.copy()
    qdict_no_sort.pop("sort", None)
    qs_no_sort = qdict_no_sort.urlencode()
    qs_no_sort = f"&{qs_no_sort}" if qs_no_sort else ""

    ctx = {
        "tickets": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "page_size": page_size,
        "filters": {
            "q": q,
            "status": status,
            "category": category,
            "priority": priority,
        },
        "statuses": statuses,
        "qs_no_page": qs_no_page,  # opcional para los links de paginación
        "qs_no_sort": qs_no_sort,
        "other_tickets": other_tickets,
    }
    return TemplateResponse(request, "tickets/list.html", ctx)


@login_required
def ticket_create(request):
    ...
    if request.method == "POST":
        form = TicketCreateForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.requester = request.user
            t.status = Ticket.OPEN
            t.code = f"TCK-{uuid.uuid4().hex[:8].upper()}"
            t.save()

            # ⬇️ Si no se asignó manualmente, intenta auto-asignar por reglas
            if not t.assigned_to_id:
                try:
                    apply_auto_assign(t)
                except Exception:
                    pass

            messages.success(request, f"Ticket creado: {t.code}")
            return redirect("ticket_detail", pk=t.pk)
        messages.error(request, "Revisa los campos del formulario.")
    else:
        form = TicketCreateForm()
    return TemplateResponse(request, "tickets/new.html", {"form": form})


@login_required
def ticket_detail(request, pk):
    """Detalle + panel de gestión + comentarios/adjuntos (HTMX)."""
    t = get_object_or_404(
        Ticket.objects.select_related(
            "category", "priority", "area", "requester", "assigned_to"
        ),
        pk=pk,
    )
    u = request.user
    if not (is_admin(u) or is_tech(u) or t.requester_id == u.id):
        return HttpResponseForbidden("No autorizado")

    # Panel de gestión
    is_admin_u = is_admin(u)
    is_tech_u = is_tech(u)
    can_assign = is_admin_u or is_tech_u
    allowed = allowed_transitions_for(t, u)

    tech_users = []
    if is_admin_u:
        try:
            g = Group.objects.get(name="TECH")
            tech_users = list(
                User.objects.filter(groups=g, is_active=True).order_by("username")
            )
        except Group.DoesNotExist:
            tech_users = []

    ctx = {
        "t": t,
        "can_assign": can_assign,
        "allowed_transitions": allowed,
        "tech_users": tech_users,
        "is_admin_u": is_admin_u,
        "is_tech_u": is_tech_u,
    }
    return TemplateResponse(request, "tickets/detail.html", ctx)


@login_required
def ticket_print(request, pk):
    """Vista imprimible (PDF con Ctrl+P)."""
    t = get_object_or_404(
        Ticket.objects.select_related(
            "category", "priority", "area", "requester", "assigned_to"
        ),
        pk=pk,
    )
    u = request.user
    if not (
        is_admin(u)
        or (is_tech(u) and t.assigned_to_id in (None, u.id))
        or t.requester_id == u.id
    ):
        return HttpResponseForbidden("No autorizado")
    return TemplateResponse(request, "tickets/print.html", {"t": t})


# --------- partials HTMX ---------
@login_required
def comments_partial(request, pk):
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    if not (is_admin(u) or is_tech(u) or t.requester_id == u.id):
        return HttpResponseForbidden("No autorizado")
    qs = TicketComment.objects.filter(ticket=t).order_by("created_at")
    if not (is_admin(u) or is_tech(u)):
        qs = qs.filter(is_internal=False)
    return TemplateResponse(
        request, "tickets/partials/comments.html", {"t": t, "comments": qs}
    )


@login_required
def attachments_partial(request, pk):
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    if not (
        is_admin(u)
        or (is_tech(u) and t.assigned_to_id in (None, u.id))
        or t.requester_id == u.id
    ):
        return HttpResponseForbidden("No autorizado")
    qs = TicketAttachment.objects.filter(ticket=t).order_by("-uploaded_at")
    return TemplateResponse(
        request, "tickets/partials/attachments.html", {"t": t, "attachments": qs}
    )


# --------- acciones UI ---------
@login_required 
@require_http_methods(["POST"])
def add_comment(request, pk):
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    if not (is_admin(u) or is_tech(u) or t.requester_id == u.id):
        return HttpResponseForbidden("No autorizado")

    body = (request.POST.get("body") or "").strip()
    if not body:
        return HttpResponseBadRequest("Comentario vacío")

    is_internal = request.POST.get("is_internal") == "on"
    if not (is_admin(u) or is_tech(u)):
        # REQUESTER no puede marcar interno
        is_internal = False

    # Crear comentario
    c = TicketComment.objects.create(
        ticket=t, author=u, body=body, is_internal=is_internal
    )

    # Registrar en auditoría
    AuditLog.objects.create(
        ticket=t,
        actor=u,
        action="COMMENT",
        meta={"internal": bool(is_internal)}
    )

    # Volver a cargar la lista de comentarios (ocultando internos a requester)
    qs = TicketComment.objects.filter(ticket=t).order_by("created_at")
    if not (is_admin(u) or is_tech(u)):
        qs = qs.filter(is_internal=False)

    return TemplateResponse(
        request, "tickets/partials/comments.html", {"t": t, "comments": qs}
    )


@login_required
@require_http_methods(["POST"])
def add_attachment(request, pk):
    """Sube adjunto desde la UI (misma política que la API)."""
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    if not (
        is_admin(u)
        or (is_tech(u) and t.assigned_to_id in (None, u.id))
        or t.requester_id == u.id
    ):
        return HttpResponseForbidden("No autorizado")

    f = request.FILES.get("file")
    if not f:
        return HttpResponseBadRequest("Archivo requerido")
    if f.size > 20 * 1024 * 1024:
        return HttpResponseBadRequest("Archivo > 20MB")

    # --- Validación de tipo/extension (whitelist) ---
    allowed_ext = {"pdf", "png", "jpg", "jpeg", "txt", "csv", "log", "docx", "xlsx"}
    allowed_ct_prefix = ("image/",)
    allowed_ct_exact = {
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    name_lower = f.name.lower()
    ext = name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""
    content_type = getattr(f, "content_type", "") or ""

    if (ext not in allowed_ext) or not (
        content_type.startswith(allowed_ct_prefix) or content_type in allowed_ct_exact
    ):
        return HttpResponseBadRequest("Tipo de archivo no permitido")

    TicketAttachment.objects.create(
        ticket=t, uploaded_by=u, file=f,
        content_type=content_type, size=f.size
    )


@login_required
@require_http_methods(["POST"])
def ticket_assign(request, pk):
    """Asignar/reasignar desde UI. ADMIN elige técnico; TECH se auto-asigna."""
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user

    if not (is_admin(u) or is_tech(u)):
        return HttpResponseForbidden("No autorizado para asignar")

    # ADMIN: combo; TECH: auto-asignación
    to_user_id = request.POST.get("to_user_id")
    if is_tech(u) and not is_admin(u):
        to_user_id = str(u.id)

    if not to_user_id:
        messages.error(request, "Debes seleccionar un técnico.")
        return redirect("ticket_detail", pk=t.pk)

    try:
        to_user = User.objects.get(id=to_user_id, is_active=True)
    except User.DoesNotExist:
        messages.error(request, "Técnico no válido.")
        return redirect("ticket_detail", pk=t.pk)

    # Si es ADMIN, valida que sea TECH
    if is_admin(u):
        try:
            g = Group.objects.get(name="TECH")
        except Group.DoesNotExist:
            messages.error(request, "No existe el grupo TECH.")
            return redirect("ticket_detail", pk=t.pk)
        if not to_user.groups.filter(id=g.id).exists():
            messages.error(request, "El usuario seleccionado no es TECH.")
            return redirect("ticket_detail", pk=t.pk)

    reason = (request.POST.get("reason") or "").strip()
    prev = t.assigned_to
    t.assigned_to = to_user
    t.save(update_fields=["assigned_to", "updated_at"])

    TicketAssignment.objects.create(
        ticket=t, from_user=u, to_user=to_user, reason=reason
    )
    AuditLog.objects.create(
        ticket=t,
        actor=u,
        action="ASSIGN",
        meta={"from": prev.id if prev else None, "to": to_user.id, "reason": reason},
    )

    messages.success(request, f"Ticket asignado a {to_user.username}.")
    return redirect("ticket_detail", pk=t.pk)


@login_required
@require_http_methods(["POST"])
def ticket_transition(request, pk):
    """Cambiar estado desde UI (ADMIN o TECH asignado). Puede incluir comentario (interno/público)."""
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user

    allowed = allowed_transitions_for(t, u)
    if not allowed:
        return HttpResponseForbidden("No autorizado a cambiar estado")

    next_status = request.POST.get("next_status")
    comment = (request.POST.get("comment") or "").strip()
    is_internal = request.POST.get("is_internal") == "on"

    if next_status not in allowed:
        messages.error(
            request, f"Transición no permitida desde {t.status} a {next_status}."
        )
        return redirect("ticket_detail", pk=t.pk)

    t.status = next_status
    if next_status == Ticket.RESOLVED:
        t.resolved_at = timezone.now()
    if next_status == Ticket.CLOSED:
        t.closed_at = timezone.now()
    t.save()

    if comment:
        TicketComment.objects.create(
            ticket=t, author=u, body=comment, is_internal=is_internal
        )

    AuditLog.objects.create(
        ticket=t,
        actor=u,
        action="STATUS",
        meta={
            "to": next_status,
            "with_comment": bool(comment),
            "internal": bool(is_internal),
        },
    )

    messages.success(request, f"Estado actualizado a {next_status}.")
    return redirect("ticket_detail", pk=t.pk)


# ----------------- Reportes (dashboard) -----------------
@login_required
def reports_dashboard(request):
    u = request.user
    qs = Ticket.objects.all()  # NO select_related para evitar FieldError

    # Visibilidad por rol
    if is_admin(u):
        pass
    elif is_tech(u):
        qs = qs.filter(assigned_to=u)
    else:
        qs = qs.filter(requester=u)

    # Filtro por fechas (rango en created_at)
    dfrom = _parse_date_param(request.GET.get("from"))
    dto = _parse_date_param(request.GET.get("to"))
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom)
    if dto:
        qs = qs.filter(created_at__date__lte=dto)

    tech_selected = (request.GET.get("tech") or "").strip()
    if tech_selected:
        qs = qs.filter(assigned_to_id=tech_selected)

    report_type = request.GET.get("type", "total")

    # Métricas base
    by_status_raw = dict(qs.values_list("status").annotate(c=Count("id")))
    status_map = dict(Ticket.STATUS_CHOICES)
    by_status = {status_map.get(k, k): v for k, v in by_status_raw.items()}
    by_category = list(
        qs.values("category__name").annotate(count=Count("id")).order_by("-count")
    )
    by_priority = list(
        qs.values("priority__name").annotate(count=Count("id")).order_by("-count")
    )
    by_area = list(
        qs.values("area__name")
            .annotate(count=Count("id"))
            .order_by("-count")
    )
    by_tech = list(
        qs.exclude(assigned_to__isnull=True)
        .values("assigned_to__username")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # TPR (horas)
    dur = ExpressionWrapper(
        F("resolved_at") - F("created_at"), output_field=DurationField()
    )
    resolved = qs.exclude(resolved_at__isnull=True)
    avg_resolve = resolved.aggregate(avg=Avg(dur))["avg"]
    avg_hours = round(avg_resolve.total_seconds() / 3600, 2) if avg_resolve else None

    # Datos para Chart.js
    chart_cat = {
        "labels": [r["category__name"] or "—" for r in by_category],
        "data": [r["count"] for r in by_category],
    }
    chart_pri = {
        "labels": [r["priority__name"] or "—" for r in by_priority],
        "data": [r["count"] for r in by_priority],
    }
    chart_tech = {
        "labels": [r["assigned_to__username"] or "—" for r in by_tech],
        "data": [r["count"] for r in by_tech],
    }

    # Histograma de horas
    bins = [
        (0, 4, "0–4h"),
        (4, 8, "4–8h"),
        (8, 24, "8–24h"),
        (24, 48, "24–48h"),
        (48, 72, "48–72h"),
        (72, 120, "72–120h"),
        (120, None, "120h+"),
    ]
    durations = [
        (t.resolved_at - t.created_at).total_seconds() / 3600.0
        for t in resolved.only("created_at", "resolved_at")
    ]
    hist_counts = [0] * len(bins)
    for h in durations:
        for i, (lo, hi, _) in enumerate(bins):
            if (h >= lo) and (hi is None or h < hi):
                hist_counts[i] += 1
                break
    chart_hist = {"labels": [label for _, _, label in bins], "data": hist_counts}

    # Categorías más lentas
    by_cat_speed = list(resolved.values("category__name").annotate(avg=Avg(dur)).order_by("-avg"))
    chart_cat_slow = {
        "labels": [r["category__name"] or "—" for r in by_cat_speed[:8]],
        "data": [
            round(r["avg"].total_seconds() / 3600.0, 2) if r["avg"] else 0
            for r in by_cat_speed[:8]
        ],
    }

    return TemplateResponse(
        request,
        "reports/dashboard.html",
        {
            "total": qs.count(),
            "by_status": by_status,
            "by_category": by_category,
            "by_priority": by_priority,
            "by_area": by_area,
            "avg_hours": avg_hours,
            "is_admin_u": is_admin(request.user),
            "from": dfrom.isoformat() if dfrom else "",
            "to": dto.isoformat() if dto else "",
            "chart_cat": chart_cat,
            "chart_pri": chart_pri,
            "chart_tech": chart_tech,
            "chart_hist": chart_hist,
            "chart_cat_slow": chart_cat_slow,
            "techs": User.objects.filter(groups__name="TECH").order_by("username"),
            "tech_selected": tech_selected,
            "report_type": report_type,
        },
    )


@login_required
@require_POST
def reports_check_sla(request):
    """Ejecuta el chequeo SLA desde la web (solo ADMIN)."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Solo ADMIN")

    try:
        warn_ratio = float(request.POST.get("warn_ratio", "0.8"))
    except ValueError:
        warn_ratio = 0.8
    dry = request.POST.get("dry_run") == "on"

    result = run_sla_check(warn_ratio=warn_ratio, dry_run=dry)
    msg = f"Chequeo SLA → warnings: {result['warnings']} | breaches: {result['breaches']}"
    messages.success(request, msg + (" (dry-run)" if dry else ""))
    return redirect("reports_dashboard")


# --- PDF (xhtml2pdf) ---
@login_required
def ticket_pdf(request, pk):
    """Genera PDF de la orden desde la misma plantilla de impresión."""
    t = get_object_or_404(
        Ticket.objects.select_related(
            "category", "priority", "area", "requester", "assigned_to"
        ),
        pk=pk,
    )
    u = request.user
    if not (
        is_admin(u)
        or (is_tech(u) and t.assigned_to_id in (None, u.id))
        or t.requester_id == u.id
    ):
        return HttpResponseForbidden("No autorizado")

    template = get_template("tickets/print.html")
    html = template.render({"t": t, "for_pdf": True, "request": request})
    result = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=result, encoding="utf-8")

    if pisa_status.err:
        return HttpResponse("Error generando PDF", status=500)

    resp = HttpResponse(result.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{t.code}.pdf"'
    return resp

@login_required
def reports_pdf(request):
    """
    Genera un PDF con los KPIs del dashboard de reportes.
    Respeta los filtros ?from=YYYY-MM-DD&to=YYYY-MM-DD y la visibilidad por rol.
    """
    u = request.user
    qs = Ticket.objects.all()

    # Visibilidad por rol
    if is_admin(u):
        pass
    elif is_tech(u):
        qs = qs.filter(assigned_to=u)
    else:
        qs = qs.filter(requester=u)

    # Filtros de fecha (rango en created_at)
    dfrom = _parse_date_param(request.GET.get("from"))
    dto   = _parse_date_param(request.GET.get("to"))
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom)
    if dto:
        qs = qs.filter(created_at__date__lte=dto)

    # Métricas
    by_status   = dict(qs.values_list("status").annotate(c=Count("id")))
    by_category = list(qs.values("category__name").annotate(count=Count("id")).order_by("-count"))
    by_priority = list(qs.values("priority__name").annotate(count=Count("id")).order_by("-count"))
    by_tech     = list(
        qs.exclude(assigned_to__isnull=True)
          .values("assigned_to__username")
          .annotate(count=Count("id"))
          .order_by("-count")
    )

    dur = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
    resolved = qs.exclude(resolved_at__isnull=True)
    avg_resolve = resolved.aggregate(avg=Avg(dur))["avg"]
    avg_hours = round(avg_resolve.total_seconds()/3600, 2) if avg_resolve else None

    ctx = {
        "total": qs.count(),
        "by_status": by_status,
        "by_category": by_category,
        "by_priority": by_priority,
        "by_tech": by_tech,
        "avg_hours": avg_hours,
        "from": dfrom.isoformat() if dfrom else "",
        "to": dto.isoformat() if dto else "",
        "now": timezone.localtime(),
        "user": request.user,
    }

    template = get_template("reports/dashboard_pdf.html")
    html = template.render(ctx)

    result = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=result, encoding="utf-8")
    if pisa_status.err:
        return HttpResponse("Error generando PDF", status=500)

    resp = HttpResponse(result.getvalue(), content_type="application/pdf")
    filename = "reporte_tickets.pdf"
    if dfrom or dto:
        filename = f"reporte_tickets_{(dfrom or '')}_{(dto or '')}.pdf".replace(":", "-")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@login_required
def audit_partial(request, pk):
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    # Misma regla de visibilidad que attachments/comments:
    if not (is_admin(u) or is_tech(u) or t.requester_id == u.id):
        return HttpResponseForbidden("No autorizado")

    # Traemos los últimos 50 eventos (del más nuevo al más antiguo)
    logs = (t.audit_logs
              .select_related("actor")
              .values("action","actor__username","meta","created_at")
              .order_by("-created_at")[:50])

    return TemplateResponse(request, "tickets/partials/audit.html", {"t": t, "logs": logs})


@login_required
def reports_export_excel(request):
    """Exporta a Excel (.xlsx) los tickets visibles para el usuario."""
    u = request.user
    qs = Ticket.objects.select_related(
        "category", "priority", "area", "requester", "assigned_to"
    ).order_by("-created_at")

    if is_admin(u):
        pass
    elif is_tech(u):
        qs = qs.filter(assigned_to=u)
    else:
        qs = qs.filter(requester=u)

    dfrom = _parse_date_param(request.GET.get("from"))
    dto = _parse_date_param(request.GET.get("to"))
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom)
    if dto:
        qs = qs.filter(created_at__date__lte=dto)

    status = (request.GET.get("status") or "").strip()
    category = (request.GET.get("category") or "").strip()
    priority = (request.GET.get("priority") or "").strip()
    tech = (request.GET.get("tech") or "").strip()
    q = (request.GET.get("q") or "").strip()

    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)
    if priority:
        qs = qs.filter(priority_id=priority)
    if tech:
        qs = qs.filter(assigned_to_id=tech)
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(title__icontains=q)
            | Q(description__icontains=q)
        )

    wb = tickets_to_workbook(qs)
    out = BytesIO()
    wb.save(out)
    resp = HttpResponse(
        out.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="tickets_export.xlsx"'
    return resp

@login_required
def auto_rules_list(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Solo ADMIN")
    rules = AutoAssignRule.objects.select_related("category","area","tech").order_by("-is_active","category__name","area__name")
    return TemplateResponse(request, "tickets/auto_rules/list.html", {"rules": rules})

@login_required
def auto_rule_create(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Solo ADMIN")
    if request.method == "POST":
        form = AutoAssignRuleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Regla creada.")
            return redirect("auto_rules_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = AutoAssignRuleForm()
    return TemplateResponse(request, "tickets/auto_rules/form.html", {"form": form, "is_new": True})

@login_required
def auto_rule_edit(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden("Solo ADMIN")
    rule = get_object_or_404(AutoAssignRule, pk=pk)
    if request.method == "POST":
        form = AutoAssignRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, "Regla actualizada.")
            return redirect("auto_rules_list")
        messages.error(request, "Revisa los campos.")
    else:
        form = AutoAssignRuleForm(instance=rule)
    return TemplateResponse(request, "tickets/auto_rules/form.html", {"form": form, "is_new": False})

@login_required
@require_http_methods(["POST"])
def auto_rule_toggle(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden("Solo ADMIN")
    rule = get_object_or_404(AutoAssignRule, pk=pk)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active"])
    messages.success(request, f"Regla {'activada' if rule.is_active else 'desactivada'}.")
    return redirect("auto_rules_list")

@login_required
@require_http_methods(["POST"])
def auto_rule_delete(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden("Solo ADMIN")
    rule = get_object_or_404(AutoAssignRule, pk=pk)
    rule.delete()
    messages.success(request, "Regla eliminada.")
    return redirect("auto_rules_list")

@login_required
def reports_export_pdf(request):
    """
    Exporta un PDF con los mismos KPIs del dashboard (sin gráficos).
    Respeta visibilidad por rol y rango de fechas (?from=YYYY-MM-DD&to=YYYY-MM-DD).
    """
    u = request.user
    qs = Ticket.objects.select_related("category", "priority", "assigned_to", "requester")

    # Visibilidad por rol
    if is_admin(u):
        pass
    elif is_tech(u):
        qs = qs.filter(assigned_to=u)
    else:
        qs = qs.filter(requester=u)

    # Fechas y filtros adicionales
    dfrom = _parse_date_param(request.GET.get("from"))
    dto   = _parse_date_param(request.GET.get("to"))
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom)
    if dto:
        qs = qs.filter(created_at__date__lte=dto)

    tech_id = (request.GET.get("tech") or "").strip()
    if tech_id:
        qs = qs.filter(assigned_to_id=tech_id)

    report_type = request.GET.get("type", "total")

    dur = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
    resolved = qs.exclude(resolved_at__isnull=True)
    avg_resolve = resolved.aggregate(avg=Avg(dur))["avg"]
    avg_hours = round(avg_resolve.total_seconds()/3600, 2) if avg_resolve else None

    status_map = dict(Ticket.STATUS_CHOICES)
    ctx = {
        "generated_at": timezone.now(),
        "from": dfrom.isoformat() if dfrom else "",
        "to": dto.isoformat() if dto else "",
        "total": qs.count(),
        "type": report_type,
    }

    if report_type == "categoria":
        ctx["by_category"] = list(
            qs.values("category__name").annotate(count=Count("id")).order_by("-count")
        )
    elif report_type == "promedio":
        ctx["avg_hours"] = avg_hours
    elif report_type == "tecnico":
        ctx["by_tech"] = list(
            qs.exclude(assigned_to__isnull=True)
            .values("assigned_to__username")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
    else:
        by_status_raw = dict(qs.values_list("status").annotate(c=Count("id")))
        ctx["by_status"] = {status_map.get(k, k): v for k, v in by_status_raw.items()}
        ctx["by_category"] = list(
            qs.values("category__name").annotate(count=Count("id")).order_by("-count")
        )
        ctx["by_priority"] = list(
            qs.values("priority__name").annotate(count=Count("id")).order_by("-count")
        )
        ctx["avg_hours"] = avg_hours

    # Render y PDF
    html = get_template("reports/report_pdf.html").render(ctx)
    result = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=result, encoding="utf-8")
    if pisa_status.err:
        return HttpResponse("Error generando PDF", status=500)

    resp = HttpResponse(result.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="reporte_tickets.pdf"'
    return resp
