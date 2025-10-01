# tickets/views.py
from __future__ import annotations

# --- Django core ---
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.http import (
    HttpResponseForbidden,
    HttpResponseBadRequest,
    HttpResponse,
)

from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.template.response import TemplateResponse
from django.template.loader import get_template
from django.utils import timezone
from django.utils.timezone import localtime


from django.shortcuts import render
from .forms import AutoAssignRuleForm, FAQForm
from .models import AutoAssignRule, FAQ

# --- Stdlib ---
from datetime import datetime, timedelta
import json
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
    EventLog,
    Notification,
    Priority,
)


from accounts.roles import is_admin, is_tech, ROLE_TECH, ROLE_ADMIN  # helpers de rol
from .services import run_sla_check, apply_auto_assign, tickets_to_workbook
from .validators import validate_upload, UploadValidationError

User = get_user_model()


# ----------------- notificaciones -----------------
def create_notification(user, message, url=""):
    if user:
        Notification.objects.create(user=user, message=message, url=url)


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


def can_upload_attachments(ticket: Ticket, user) -> bool:
    """Regla centralizada de quién puede subir/consultar adjuntos."""

    return bool(
        is_admin(user)
        or (is_tech(user) and ticket.assigned_to_id in (None, user.id))
        or ticket.requester_id == user.id
    )


def discussion_payload(ticket: Ticket, user) -> dict:
    """Construye el contexto con los comentarios visibles para el usuario."""

    comments_qs = TicketComment.objects.filter(ticket=ticket).order_by("created_at")
    if not (is_admin(user) or is_tech(user)):
        comments_qs = comments_qs.filter(is_internal=False)

    attachments_qs = TicketAttachment.objects.filter(ticket=ticket).order_by("-uploaded_at")
    can_manage_attachments = can_upload_attachments(ticket, user)

    return {
        "t": ticket,
        "comments": comments_qs,
        "attachments": attachments_qs,
        "can_upload_files": can_manage_attachments,
    }


# ----------------- vistas UI -----------------
@login_required
def dashboard(request):
    """Panel con indicadores clave según rol."""
    u = request.user
    base = Ticket.objects.all()
    if is_admin(u):
        qs = base
        scope = "global"
    elif is_tech(u):
        if u.has_perm("tickets.view_all_tickets"):
            qs = base
            scope = "de todos los tickets"
        else:
            qs = base.filter(assigned_to=u)
            scope = "de tus tickets asignados"
    else:
        qs = base.filter(requester=u)
        scope = "de tus tickets"

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    counts = {
        "open": qs.filter(status=Ticket.OPEN).count(),
        "in_progress": qs.filter(status=Ticket.IN_PROGRESS).count(),
        "resolved": qs.filter(resolved_at__gte=month_start).count(),
        "closed": qs.filter(closed_at__gte=month_start).count(),
    }

    chart_labels = ["Abierto", "En progreso", "Resuelto (mes)", "Cerrado (mes)"]
    chart_data = json.dumps({
        "labels": chart_labels,
        "data": [
            counts["open"],
            counts["in_progress"],
            counts["resolved"],
            counts["closed"],
        ],
    })

    urgent_candidates = (
        qs.filter(status__in=[Ticket.OPEN, Ticket.IN_PROGRESS])
        .select_related("priority")
        .order_by("created_at")
    )
    urgent_tickets = []
    for ticket in urgent_candidates:
        sla_hours = getattr(ticket.priority, "sla_hours", 72) or 72
        if ticket.is_overdue or ticket.is_warning or sla_hours <= 24:
            urgent_tickets.append(ticket)
    urgent_tickets.sort(key=lambda t: t.remaining_hours)

    cutoff = timezone.now() - timedelta(days=60)
    failure_qs = qs.filter(created_at__gte=cutoff)
    failure_rows = (
        failure_qs.values("category__name")
        .annotate(total=Count("id"))
        .order_by("-total", "category__name")[:15]
    )
    palette = [
        "#2563eb",
        "#7c3aed",
        "#f97316",
        "#059669",
        "#dc2626",
        "#0891b2",
        "#9333ea",
        "#f59e0b",
        "#0ea5e9",
        "#14b8a6",
        "#ef4444",
        "#8b5cf6",
        "#38bdf8",
        "#34d399",
        "#fb923c",
    ]
    failure_breakdown = []
    for idx, row in enumerate(failure_rows):
        label = row["category__name"] or "Sin categoría"
        failure_breakdown.append(
            {
                "label": label,
                "total": row["total"],
                "color": palette[idx % len(palette)],
            }
        )

    failure_labels = [item["label"] for item in failure_breakdown]
    failure_totals = [item["total"] for item in failure_breakdown]
    failures_chart_data = json.dumps(
        {
            "labels": failure_labels,
            "data": failure_totals,
            "colors": [item["color"] for item in failure_breakdown],
            "since": cutoff.date().isoformat(),
        }
    )

    ctx = {
        "counts": counts,
        "chart_data": chart_data,
        "scope": scope,
        "urgent_tickets": urgent_tickets,
        "failures_chart_data": failures_chart_data,
        "has_failures_data": bool(failure_totals),
        "failures_since": cutoff,
        "failure_breakdown": failure_breakdown,
    }
    return render(request, "dashboard.html", ctx)


@login_required
def faq_list(request):
    """Listado de preguntas frecuentes y formulario de alta rápida."""
    user = request.user
    can_manage = is_admin(user) or is_tech(user)
    faqs = FAQ.objects.all()

    form = FAQForm()
    if request.method == "POST":
        if not can_manage:
            return HttpResponseForbidden("Sin autorización")
        form = FAQForm(request.POST)
        if form.is_valid():
            faq = form.save(commit=False)
            faq.created_by = user
            faq.updated_by = user
            faq.save()
            messages.success(request, "Pregunta frecuente creada.")
            return redirect("faq_list")

    ctx = {
        "faqs": faqs,
        "form": form,
        "can_manage": can_manage,
    }
    return render(request, "tickets/faq.html", ctx)


@login_required
def faq_edit(request, pk):
    """Editar una pregunta frecuente existente."""
    faq = get_object_or_404(FAQ, pk=pk)
    user = request.user
    if not (is_admin(user) or is_tech(user)):
        return HttpResponseForbidden("Sin autorización")

    if request.method == "POST":
        form = FAQForm(request.POST, instance=faq)
        if form.is_valid():
            updated = form.save(commit=False)
            if not updated.created_by_id:
                updated.created_by = user
            updated.updated_by = user
            updated.save()
            messages.success(request, "Pregunta frecuente actualizada.")
            return redirect("faq_list")
    else:
        form = FAQForm(instance=faq)

    return render(
        request,
        "tickets/faq_form.html",
        {
            "form": form,
            "faq": faq,
        },
    )


@login_required
@require_POST
def faq_delete(request, pk):
    """Elimina una pregunta frecuente."""
    user = request.user
    if not (is_admin(user) or is_tech(user)):
        return HttpResponseForbidden("Sin autorización")

    faq = get_object_or_404(FAQ, pk=pk)
    faq.delete()
    messages.success(request, "Pregunta frecuente eliminada.")
    return redirect("faq_list")


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
    can_view_all = u.has_perm("tickets.view_all_tickets") if is_tech(u) else False

    inbox = (request.GET.get("inbox") or "").strip().lower()
    inbox_options: list[tuple[str, str]] = []
    if is_admin(u):
        default_inbox = "general"
        if inbox not in {"general", "personal"}:
            inbox = default_inbox
        qs = base_qs if inbox == "general" else base_qs.filter(assigned_to=u)
        inbox_options = [
            ("general", "Bandeja general"),
            ("personal", "Bandeja personal"),
        ]
    elif is_tech(u):
        allowed_inboxes = {"personal"}
        if can_view_all:
            allowed_inboxes.add("general")
        default_inbox = "general" if can_view_all else "personal"
        if inbox not in allowed_inboxes:
            inbox = default_inbox
        if inbox == "general" and can_view_all:
            qs = base_qs
        else:
            qs = base_qs.filter(assigned_to=u)
        inbox_options = []
        if can_view_all:
            inbox_options.append(("general", "Bandeja general"))
        inbox_options.append(("personal", "Bandeja personal"))
    else:
        qs = base_qs.filter(requester=u)
        inbox = ""

    # Filtros
    status = (request.GET.get("status") or "").strip()
    category = (request.GET.get("category") or "").strip()
    priority = (request.GET.get("priority") or "").strip()
    alerts_only = request.GET.get("alerts") == "1"
    hide_closed = request.GET.get("hide_closed", "0")
    if hide_closed not in {"0", "1"}:
        hide_closed = "0"

    # Ocultar tickets cerrados solo si el usuario lo solicita explícitamente
    if hide_closed == "1" and not status:
        qs = qs.exclude(status=Ticket.CLOSED)

    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)
    if priority:
        if priority.isdigit():
            qs = qs.filter(priority_id=priority)
        else:
            qs = qs.filter(priority__name__iexact=priority)

    # Búsqueda
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
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
        "kind",
    }
    sort_key = sort.lstrip("-")
    if sort_key in allowed_sorts:
        qs = qs.order_by(sort)
    else:
        qs = qs.order_by("-created_at")

    # Paginación
    try:
        page_size = int(request.GET.get("page_size", 20))
    except ValueError:
        page_size = 20
    page_size = max(5, min(page_size, 100))  # clamp 5..100

    tickets_list = list(qs)
    if alerts_only:
        tickets_list = [t for t in tickets_list if t.is_overdue or t.is_warning]

    paginator = Paginator(tickets_list, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Resumen exclusivo para técnicos: permite decidir si autoasignarse.
    tech_counters = None
    if is_tech(u):
        tech_counters = {
            "assigned": Ticket.objects.exclude(status=Ticket.CLOSED)
            .filter(assigned_to=u)
            .count(),
            "total": Ticket.objects.exclude(status=Ticket.CLOSED).count(),
            "unassigned": Ticket.objects.exclude(status=Ticket.CLOSED)
            .filter(assigned_to__isnull=True)
            .count(),
        }

    # Para el combo de estados (clave y etiqueta en español)
    statuses = Ticket.STATUS_CHOICES
    priorities = list(Priority.objects.order_by("name"))

    # Para preservar filtros en paginación (opcional, usado en template)
    qdict = request.GET.copy()
    qdict.pop("page", None)
    qs_no_page = qdict.urlencode()
    qs_no_page = f"&{qs_no_page}" if qs_no_page else ""

    qdict_no_sort = qdict.copy()
    qdict_no_sort.pop("sort", None)
    qs_no_sort = qdict_no_sort.urlencode()
    qs_no_sort = f"&{qs_no_sort}" if qs_no_sort else ""

    def _inbox_query(value: str) -> str:
        params = request.GET.copy()
        params.pop("page", None)
        if value:
            params["inbox"] = value
        else:
            params.pop("inbox", None)
        encoded = params.urlencode()
        return f"?{encoded}" if encoded else "?"

    inbox_links = [
        {"value": value, "label": label, "url": _inbox_query(value)}
        for value, label in inbox_options
    ]

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
            "alerts": "1" if alerts_only else "",
            "hide_closed": hide_closed,
        },
        "statuses": statuses,
        "qs_no_page": qs_no_page,  # opcional para los links de paginación
        "qs_no_sort": qs_no_sort,
        "tech_counters": tech_counters,
        "priorities": priorities,
        "current_inbox": inbox,
        "inbox_links": inbox_links,
    }
    return TemplateResponse(request, "tickets/list.html", ctx)


@login_required
def ticket_create(request):
    """Renderiza el formulario de creación y procesa el envío del ticket."""
    if request.method == "POST":
        form = TicketCreateForm(request.POST, user=request.user)
        if form.is_valid():
            assignee = None
            if "assignee" in form.cleaned_data:
                assignee = form.cleaned_data.get("assignee")
            t = form.save(commit=False)
            t.requester = request.user
            t.status = Ticket.OPEN
            if assignee:
                t.assigned_to = assignee
            t.save()

            if assignee:
                TicketAssignment.objects.create(
                    ticket=t, from_user=request.user, to_user=assignee, reason=""
                )
                AuditLog.objects.create(
                    ticket=t,
                    actor=request.user,
                    action="ASSIGN",
                    meta={
                        "from": None,
                        "from_username": None,
                        "to": assignee.id,
                        "to_username": assignee.username,
                        "reason": "",
                    },
                )

            # ⬇️ Si no se asignó manualmente, intenta auto-asignar por reglas
            if not t.assigned_to_id:
                try:
                    apply_auto_assign(t)
                except Exception:
                    pass

            link = reverse("ticket_detail", args=[t.pk])
            create_notification(request.user, f"Ticket {t.code} creado", link)
            if t.assigned_to_id:
                create_notification(t.assigned_to, f"Ticket {t.code} te ha sido asignado", link)

            messages.success(request, f"Ticket {t.code} creado con éxito.")
            return redirect("ticket_detail", pk=t.pk)
        messages.error(request, "Revisa los campos del formulario.")
    else:
        form = TicketCreateForm(user=request.user)
    return TemplateResponse(request, "tickets/new.html", {"form": form})


@login_required
def notifications_list(request):
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")
    qs.filter(is_read=False).update(is_read=True)
    return TemplateResponse(request, "notifications/list.html", {"notifications": qs})


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
        return HttpResponseForbidden("Sin autorización")

    # Panel de gestión
    is_admin_u = is_admin(u)
    is_tech_u = is_tech(u)
    can_assign = is_admin_u or is_tech_u
    allowed_codes = allowed_transitions_for(t, u)
    status_map = dict(Ticket.STATUS_CHOICES)
    allowed = [(code, status_map.get(code, code)) for code in allowed_codes]

    tech_users = []
    if is_admin_u:
        try:
            g = Group.objects.get(name=ROLE_TECH)
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
        "can_mark_internal": is_admin_u or is_tech_u,
        "can_upload_files": can_upload_attachments(t, u),
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
        return HttpResponseForbidden("Sin autorización")
    return TemplateResponse(request, "tickets/print.html", {"t": t})


# --------- partials HTMX ---------
@login_required
def discussion_partial(request, pk):
    """HTMX: renderiza el historial de comentarios en un solo bloque."""

    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    if not (is_admin(u) or is_tech(u) or t.requester_id == u.id):
        return HttpResponseForbidden("Sin autorización")

    payload = discussion_payload(t, u)
    return TemplateResponse(request, "tickets/partials/discussion.html", payload)


# --------- acciones UI ---------
@login_required
@require_http_methods(["POST"])
def add_comment(request, pk):
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user
    if not (is_admin(u) or is_tech(u) or t.requester_id == u.id):
        return HttpResponseForbidden("Sin autorización")

    body = (request.POST.get("body") or "").strip()
    if not body:
        return HttpResponseBadRequest("Comentario vacío")

    is_internal = request.POST.get("is_internal") == "on"
    if not (is_admin(u) or is_tech(u)):
        # SOLICITANTE no puede marcar interno
        is_internal = False

    uploaded_file = request.FILES.get("file")
    if uploaded_file and not can_upload_attachments(t, u):
        return HttpResponseForbidden("Sin autorización para adjuntar")

    if uploaded_file:
        try:
            validate_upload(uploaded_file)
        except UploadValidationError as e:
            return HttpResponseBadRequest(str(e))

    # Crear comentario principal
    comment = TicketComment.objects.create(
        ticket=t, author=u, body=body, is_internal=is_internal
    )

    attachment = None
    if uploaded_file:
        content_type = getattr(uploaded_file, "content_type", "") or ""
        attachment = TicketAttachment.objects.create(
            ticket=t,
            uploaded_by=u,
            file=uploaded_file,
            content_type=content_type,
            size=uploaded_file.size,
        )

    attachment_name = None
    if attachment:
        attachment_name = attachment.file.name.rsplit("/", 1)[-1]
    elif uploaded_file:
        attachment_name = getattr(uploaded_file, "name", None)

    # Registrar en auditoría y dejar trazabilidad para el EventLog
    AuditLog.objects.create(
        ticket=t,
        actor=u,
        action="COMMENT",
        meta={
            "internal": bool(is_internal),
            "comment_id": comment.id,
            "with_attachment": bool(attachment),
            "filename": attachment_name,
            "body_preview": body[:120],
        },
    )

    payload = discussion_payload(t, u)
    return TemplateResponse(request, "tickets/partials/discussion.html", payload)


@login_required
@require_http_methods(["POST"])
def ticket_assign(request, pk):
    """Asignar/reasignar desde UI. ADMINISTRADOR elige técnico; TECNICO se autoasigna."""
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user

    if not (is_admin(u) or is_tech(u)):
        return HttpResponseForbidden("Sin autorización para asignar")

    # ADMINISTRADOR: combo; TECNICO: autoasignación
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

    # Si es ADMINISTRADOR, valida que sea TECNICO
    if is_admin(u):
        try:
            g = Group.objects.get(name=ROLE_TECH)
        except Group.DoesNotExist:
            messages.error(request, f"No existe el grupo {ROLE_TECH}.")
            return redirect("ticket_detail", pk=t.pk)
        if not to_user.groups.filter(id=g.id).exists():
            messages.error(request, f"El usuario seleccionado no es {ROLE_TECH}.")
            return redirect("ticket_detail", pk=t.pk)

    reason = (request.POST.get("reason") or "").strip()
    new_title = (request.POST.get("new_title") or "").strip()
    prev = t.assigned_to
    previous_title = t.title

    can_rename = is_admin(u) or (is_tech(u) and str(u.id) == to_user_id)
    title_changed = False
    if can_rename and new_title and new_title != t.title:
        t.title = new_title
        title_changed = True

    t.assigned_to = to_user
    update_fields = ["assigned_to", "updated_at"]
    if title_changed:
        update_fields.append("title")
    t.save(update_fields=update_fields)

    TicketAssignment.objects.create(
        ticket=t, from_user=u, to_user=to_user, reason=reason
    )
    AuditLog.objects.create(
        ticket=t,
        actor=u,
        action="ASSIGN",
        meta={
            "from": prev.id if prev else None,
            "from_username": getattr(prev, "username", None) if prev else None,
            "to": to_user.id,
            "to_username": to_user.username,
            "reason": reason,
            "title_changed": title_changed,
            "title_from": previous_title,
            "title_to": t.title,
        },
    )

    link = reverse("ticket_detail", args=[t.pk])
    create_notification(to_user, f"Ticket {t.code} te ha sido asignado", link)
    create_notification(t.requester, f"Ticket {t.code} asignado a {to_user.username}", link)

    msg = f"Ticket asignado a {to_user.username}."
    if title_changed:
        msg += " Título actualizado."
    messages.success(request, msg)
    return redirect("ticket_detail", pk=t.pk)


@login_required
@require_http_methods(["POST"])
def ticket_transition(request, pk):
    """Cambiar estado desde UI (ADMINISTRADOR o TECNICO asignado). Puede incluir comentario (interno/público)."""
    t = get_object_or_404(Ticket, pk=pk)
    u = request.user

    allowed = allowed_transitions_for(t, u)
    if not allowed:
        return HttpResponseForbidden("Sin autorización para cambiar estado")

    next_status = request.POST.get("next_status")
    comment = (request.POST.get("comment") or "").strip()
    is_internal = request.POST.get("is_internal") == "on"

    if next_status not in allowed:
        messages.error(
            request, f"Transición no permitida desde {t.status} a {next_status}."
        )
        return redirect("ticket_detail", pk=t.pk)

    previous_status = t.status
    t._status_changed_by = u
    t._skip_status_signal_audit = True
    t.status = next_status
    if next_status == Ticket.RESOLVED:
        t.resolved_at = timezone.now()
    if next_status == Ticket.CLOSED:
        t.closed_at = timezone.now()
    t.save()

    comment_obj = None
    if comment:
        comment_obj = TicketComment.objects.create(
            ticket=t, author=u, body=comment, is_internal=is_internal
        )

    previous_status = getattr(t, "_old_status", None) or previous_status
    status_map = dict(Ticket.STATUS_CHOICES)
    AuditLog.objects.create(
        ticket=t,
        actor=u,
        action="STATUS",
        meta={
            "from": previous_status,
            "from_label": status_map.get(previous_status),
            "to": next_status,
            "to_label": status_map.get(next_status),
            "with_comment": bool(comment),
            "internal": bool(is_internal),
            "comment_id": getattr(comment_obj, "id", None),
            "body_preview": comment_obj.body[:120] if comment_obj else "",
        },
    )

    link = reverse("ticket_detail", args=[t.pk])
    msg = f"Ticket {t.code} estado actualizado a {t.get_status_display()}"
    create_notification(t.requester, msg, link)
    if t.assigned_to:
        create_notification(t.assigned_to, msg, link)

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
    if report_type == "urgencia":
        qs = qs.filter(priority__name__icontains="urgencia")

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
            "techs": User.objects.filter(groups__name=ROLE_TECH).order_by("username"),
            "tech_selected": tech_selected,
            "report_type": report_type,
        },
    )


@login_required
@require_POST
def reports_check_sla(request):
    """Ejecuta el chequeo SLA desde la web (solo ADMINISTRADOR)."""
    if not is_admin(request.user):
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")

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
        return HttpResponseForbidden("Sin autorización")

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
        return HttpResponseForbidden("Sin autorización")

    # Traemos los últimos 50 eventos (del más nuevo al más antiguo)
    logs = list(
        t.audit_logs.select_related("actor").order_by("-created_at")[:50]
    )

    action_labels = {
        "CREATE": "Creación",
        "ASSIGN": "Asignación",
        "STATUS": "Estado",
        "COMMENT": "Comentario",
        "ATTACH": "Adjunto",
        "SLA_WARN": "Alerta SLA",
        "SLA_BREACH": "SLA vencido",
    }
    status_map = dict(Ticket.STATUS_CHOICES)

    user_ids: set[int] = set()
    for log in logs:
        meta = log.meta or {}
        for key in ("from", "to"):
            val = meta.get(key)
            if isinstance(val, int):
                user_ids.add(val)
            elif isinstance(val, str) and val.isdigit():
                user_ids.add(int(val))

    user_map = {
        user.id: user.username
        for user in User.objects.filter(id__in=user_ids).only("id", "username")
    }

    def _user_name(meta: dict, key_id: str, key_name: str) -> str:
        if meta.get(key_name):
            return meta[key_name]
        val = meta.get(key_id)
        if not val:
            return "Sin asignar"
        if isinstance(val, str) and val.isdigit():
            val = int(val)
        return user_map.get(val, "Sin asignar")

    entries = []
    for log in logs:
        meta = log.meta or {}
        action = log.action
        description = ""
        notes: list[str] = []
        comment_text = ""
        comment_is_internal = False

        if action == "CREATE":
            description = "Ticket creado."
        elif action == "ASSIGN":
            from_name = _user_name(meta, "from", "from_username")
            to_name = _user_name(meta, "to", "to_username")
            if meta.get("from") and meta.get("from") != meta.get("to"):
                description = f"Reasignado de {from_name} a {to_name}."
            else:
                description = f"Asignado a {to_name}."
            reason = (meta.get("reason") or "").strip()
            if reason:
                notes.append(f"Motivo: {reason}")
            if meta.get("title_changed"):
                title_from = (meta.get("title_from") or "").strip() or "—"
                title_to = (meta.get("title_to") or "").strip() or "—"
                notes.append(f"Título: '{title_from}' → '{title_to}'")
        elif action == "STATUS":
            from_label = meta.get("from_label") or status_map.get(meta.get("from"))
            to_label = meta.get("to_label") or status_map.get(meta.get("to"))
            description = f"Estado cambiado de {from_label or 'Sin estado'} a {to_label or 'Sin estado'}."
            if meta.get("with_comment"):
                preview = (meta.get("body_preview") or "").strip()
                if preview:
                    comment_text = preview
                    comment_is_internal = bool(meta.get("internal"))
                else:
                    notes.append("Incluyó un comentario adicional.")
        elif action == "COMMENT":
            scope = "interno" if meta.get("internal") else "público"
            description = f"Comentario {scope}."
            comment_text = (meta.get("body_preview") or "").strip()
            if meta.get("with_attachment"):
                filename = meta.get("filename") or "archivo adjunto"
                notes.append(f"Adjunto: {filename}")
        elif action == "ATTACH":
            description = "Archivo adjunto agregado."
        elif action == "SLA_WARN":
            description = "Advertencia SLA: el ticket está próximo a vencer."
            remaining = meta.get("remaining_h")
            if remaining is not None:
                notes.append(f"Horas restantes: {remaining}")
        elif action == "SLA_BREACH":
            description = "El SLA del ticket fue incumplido."
            overdue = meta.get("overdue_h")
            if overdue is not None:
                notes.append(f"Horas de retraso: {overdue}")
        else:
            description = action_labels.get(action, action)

        entries.append(
            {
                "action": action,
                "action_label": action_labels.get(action, action),
                "actor": getattr(log.actor, "username", "(sistema)"),
                "created_at": localtime(log.created_at),
                "description": description,
                "notes": notes,
                "comment": comment_text,
                "comment_is_internal": comment_is_internal,
            }
        )

    return TemplateResponse(
        request,
        "tickets/partials/audit.html",
        {"t": t, "entries": entries},
    )


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
    report_type = (request.GET.get("type") or "").strip()
    q = (request.GET.get("q") or "").strip()

    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)
    if priority:
        qs = qs.filter(priority_id=priority)
    if tech:
        qs = qs.filter(assigned_to_id=tech)
    if report_type == "urgencia":
        qs = qs.filter(priority__name__icontains="urgencia")
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
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
    rules = AutoAssignRule.objects.select_related("category","area","tech").order_by("-is_active","category__name","area__name")
    return TemplateResponse(request, "tickets/auto_rules/list.html", {"rules": rules})

@login_required
def auto_rule_create(request):
    if not is_admin(request.user):
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
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
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
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
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
    rule = get_object_or_404(AutoAssignRule, pk=pk)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active"])
    messages.success(request, f"Regla {'activada' if rule.is_active else 'desactivada'}.")
    return redirect("auto_rules_list")

@login_required
@require_http_methods(["POST"])
def auto_rule_delete(request, pk):
    if not is_admin(request.user):
        return HttpResponseForbidden(f"Solo {ROLE_ADMIN}")
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
    elif report_type == "urgencia":
        ctx["urgent_tickets"] = list(
            qs.values("code", "title", "status").order_by("-created_at")
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


@staff_member_required
def logs_list(request):
    qs = EventLog.objects.select_related("actor").all()
    model = request.GET.get("model")
    if model == "ticket":
        qs = qs.filter(model=model)
    obj_id = request.GET.get("obj_id")
    if obj_id:
        qs = qs.filter(obj_id=obj_id)
    actor = request.GET.get("actor")
    if actor:
        qs = qs.filter(actor__username__icontains=actor)
    action = request.GET.get("action")
    if action:
        qs = qs.filter(action__icontains=action)
    resource = request.GET.get("resource")
    if resource:
        qs = qs.filter(resource_id=resource)
    dfrom = request.GET.get("from")
    if dfrom:
        qs = qs.filter(created_at__date__gte=dfrom)
    dto = request.GET.get("to")
    if dto:
        qs = qs.filter(created_at__date__lte=dto)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    params = request.GET.copy()
    params.pop("page", None)
    action_labels = {
        "CREATE": "Creación",
        "ASSIGN": "Asignación",
        "STATUS": "Estado",
        "COMMENT": "Comentario",
        "ATTACH": "Adjunto",
        "SLA_WARN": "Alerta SLA",
        "SLA_BREACH": "SLA vencido",
    }
    model_labels = {"ticket": "Ticket"}
    rows = []
    for item in page_obj:
        rows.append(
            {
                "created_at": localtime(item.created_at),
                "actor": getattr(item.actor, "username", "(sistema)"),
                "model": model_labels.get(item.model, item.model),
                "obj_id": item.obj_id,
                "action": action_labels.get(item.action, item.action),
                "message": item.message,
                "url": reverse("ticket_detail", args=[item.obj_id]) if item.model == "ticket" else "",
            }
        )

    ctx = {
        "logs": page_obj,
        "rows": rows,
        "page_obj": page_obj,
        "querystring": params.urlencode(),
        "filters": request.GET,
    }
    return TemplateResponse(request, "logs/list.html", ctx)
