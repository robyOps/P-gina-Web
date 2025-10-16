# tickets/api.py

# ------------------------- IMPORTS -------------------------
from django.utils import timezone  # para sellos de tiempo (resolved_at / closed_at)
from django.contrib.auth import get_user_model  # para obtener el modelo de usuario (custom o por defecto)

# DRF: vistas, permisos, decoradores para acciones custom, respuesta y parsers de archivos
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action  # define endpoints como /assign, /transition, etc.
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser  # subir archivos (multipart/form-data)
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

# Modelos (incluye AuditLog para trazabilidad)
from .models import (
    Ticket,              # entidad principal
    TicketComment,       # comentarios (internos/públicos)
    TicketAttachment,    # adjuntos
    TicketAssignment,    # historial de asignaciones
    AuditLog,            # historial/auditoría de acciones
    TicketLabel,
    TicketLabelSuggestion,
)

# Serializers (modelos <-> JSON)
from .serializers import (
    TicketSerializer,
    TicketCommentSerializer,
    TicketAttachmentSerializer,
    TicketAssignmentSerializer,  # útil para exponer historial de asignaciones
    TicketLabelSerializer,
    TicketLabelSuggestionSerializer,
)

# Validación de archivos subidos
from .validators import validate_upload, UploadValidationError

from .services import (
    apply_auto_assign,
    recompute_ticket_label_suggestions,
    accept_ticket_label_suggestion,
    get_label_suggestion_threshold,
    bulk_recompute_ticket_label_suggestions,
    collect_ticket_alerts,
)
from .utils import sanitize_text
from .clustering import train_ticket_clusters
import logging
import time

logger = logging.getLogger(__name__)

# Modelo de usuario activo
User = get_user_model()

# Helpers de roles
from accounts.roles import is_admin, is_tech, ROLE_ADMIN, ROLE_TECH


def filter_tickets_for_user(qs, user):
    if is_admin(user):
        return qs
    if is_tech(user):
        return qs.filter(assigned_to=user)
    return qs.filter(requester=user)


class TicketSuggestionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TicketAlertPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ------------------------- VIEWSET PRINCIPAL -------------------------
class TicketViewSet(viewsets.ModelViewSet):
    """
    CRUD de tickets + acciones custom:
      - assign: asignar/reasignar a un técnico
      - transition: cambiar estado (OPEN/IN_PROGRESS/RESOLVED/CLOSED)
      - comments: listar/crear comentarios
      - attachments: listar/subir adjuntos
      - assignments: ver historial de asignaciones
      - audit: ver historial de eventos (AuditLog)
    """

    serializer_class = TicketSerializer                     # serializer por defecto
    permission_classes = [permissions.IsAuthenticated]      # exige JWT/usuario logeado
    suggestion_pagination_class = TicketSuggestionPagination

    # Query base (con relaciones) y orden (últimos creados primero)
    queryset = (
        Ticket.objects.select_related(
            "category", "priority", "area", "requester", "assigned_to"
        ).order_by("-created_at")
    )

    # Filtros por query string (?status=&category=&priority=&area=)
    # Se omite ``cluster_id`` para mantener el listado público alineado con la UI
    # (ya no se expone como criterio en la vista principal) y reducir ruido.
    filterset_fields = ["status", "category", "priority", "area"]

    # --------- Visibilidad por rol ---------
    def get_queryset(self):
        """
        ADMINISTRADOR -> todos
        TECNICO       -> solo asignados a sí mismo
        SOLICITANTE   -> solo propios
        """
        qs = super().get_queryset()
        u = self.request.user
        if is_admin(u):
            return qs
        if is_tech(u):
            return qs.filter(assigned_to=u)
        return qs.filter(requester=u)

    def get_suggestion_paginator(self):
        if not hasattr(self, "_suggestion_paginator"):
            self._suggestion_paginator = self.suggestion_pagination_class()
        return self._suggestion_paginator

    # --------- Crear ticket ---------
    def perform_create(self, serializer):
        serializer.save(status=Ticket.OPEN)

        # Auditoría de creación
        AuditLog.objects.create(
            ticket=serializer.instance,
            actor=self.request.user,
            action="CREATE",
            meta={
                "category": serializer.instance.category_id,
                "priority": serializer.instance.priority_id,
            },
        )

        # Auto-asignación (si hay regla)
        try:
            apply_auto_assign(serializer.instance, actor=self.request.user)
        except Exception:
            # No bloquear la creación si hay un problema con reglas; deja rastro en logs
            logger.exception("Fallo auto-assign en perform_create", extra={"ticket_id": serializer.instance.id})


    # ---------- H4: Asignación ----------
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """
        Asignar/reasignar ticket:
          - ADMINISTRADOR puede asignar a cualquiera
          - TECNICO solo puede autoasignarse
          - Registra TicketAssignment y AuditLog 'ASSIGN'
        """
        ticket = self.get_object()
        u = request.user

        # Body esperado
        to_user_id = request.data.get("to_user_id")
        reason = sanitize_text(request.data.get("reason", ""))

        if not to_user_id:
            return Response({"detail": "to_user_id requerido"}, status=400)

        try:
            to_user = User.objects.get(id=to_user_id)
        except User.DoesNotExist:
            return Response({"detail": "Usuario destino no existe"}, status=404)

        if not (is_admin(u) or (is_tech(u) and to_user == u)):
            return Response({"detail": "No autorizado para asignar"}, status=403)

        prev = ticket.assigned_to
        ticket.assigned_to = to_user
        ticket.save(update_fields=["assigned_to", "updated_at"])

        TicketAssignment.objects.create(ticket=ticket, from_user=u, to_user=to_user, reason=reason)

        AuditLog.objects.create(
            ticket=ticket, actor=u, action="ASSIGN",
            meta={
                "from": prev.id if prev else None,
                "from_username": getattr(prev, "username", None) if prev else None,
                "to": to_user.id,
                "to_username": to_user.username,
                "reason": reason,
            },
        )

        return Response({"message": "Asignado", "from": prev.id if prev else None, "to": to_user.id}, status=200)

    @action(detail=False, methods=["post"], url_path="retrain-clusters")
    def retrain_clusters(self, request):
        if not (is_admin(request.user) or is_tech(request.user)):
            return Response(
                {"detail": "Solo técnicos o administradores pueden reentrenar clústeres."},
                status=status.HTTP_403_FORBIDDEN,
            )

        raw_clusters = request.data.get("clusters") or request.data.get("num_clusters")
        if raw_clusters is None:
            return Response(
                {"detail": "Debe indicar la cantidad de clústeres en 'clusters'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            clusters = int(raw_clusters)
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'clusters' debe ser un entero mayor a cero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if clusters <= 0:
            return Response(
                {"detail": "El parámetro 'clusters' debe ser un entero mayor a cero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = train_ticket_clusters(num_clusters=clusters)

        return Response(
            {
                "message": "Clusterización completada",
                "total_tickets": summary.total_tickets,
                "requested_clusters": summary.requested_clusters,
                "effective_clusters": summary.effective_clusters,
                "assignments": summary.assignments,
            }
        )

    # ---------- Etiquetas sugeridas ----------
    def _require_label_access(self, request, ticket):
        if not (is_admin(request.user) or is_tech(request.user)):
            return Response({"detail": "Solo técnicos o administradores pueden gestionar etiquetas."}, status=status.HTTP_403_FORBIDDEN)
        return None

    def _suggestions_queryset(self, ticket):
        return ticket.label_suggestions.order_by("-score", "label")

    @action(detail=True, methods=["get"], url_path="suggestions")
    def list_suggestions(self, request, pk=None):
        ticket = self.get_object()
        forbidden = self._require_label_access(request, ticket)
        if forbidden:
            return forbidden

        suggestions = self._suggestions_queryset(ticket)

        status_filter = (request.query_params.get("status") or "").lower()
        if status_filter == "pending":
            suggestions = suggestions.filter(is_accepted=False)
        elif status_filter == "accepted":
            suggestions = suggestions.filter(is_accepted=True)

        paginator = self.get_suggestion_paginator()
        page = paginator.paginate_queryset(suggestions, request, view=self)
        serializer = TicketLabelSuggestionSerializer(page, many=True)

        labels = TicketLabel.objects.filter(ticket=ticket).order_by("name")
        response = paginator.get_paginated_response(serializer.data)
        response.data["meta"] = {
            "threshold": get_label_suggestion_threshold(),
            "labels": TicketLabelSerializer(labels, many=True).data,
        }
        return response

    @action(detail=True, methods=["post"], url_path="recompute-suggestions")
    def recompute_suggestions(self, request, pk=None):
        ticket = self.get_object()
        forbidden = self._require_label_access(request, ticket)
        if forbidden:
            return forbidden

        threshold = request.data.get("threshold")
        parsed_threshold = None
        if threshold is not None:
            try:
                parsed_threshold = float(threshold)
            except (TypeError, ValueError):
                return Response({"detail": "threshold debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        result = recompute_ticket_label_suggestions(ticket, threshold=parsed_threshold)
        logger.info(
            "Recomputo de sugerencias por API",
            extra={"ticket_id": ticket.id, "actor_id": request.user.id, "metrics": result},
        )
        return Response({"detail": "Sugerencias recalculadas", "metrics": result})

    @action(
        detail=True,
        methods=["post"],
        url_path=r"suggestions/(?P<suggestion_id>[^/.]+)/accept",
    )
    def accept_suggestion(self, request, pk=None, suggestion_id=None):
        ticket = self.get_object()
        forbidden = self._require_label_access(request, ticket)
        if forbidden:
            return forbidden

        try:
            suggestion = TicketLabelSuggestion.objects.get(id=suggestion_id, ticket=ticket)
        except TicketLabelSuggestion.DoesNotExist:
            return Response({"detail": "Sugerencia no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if suggestion.is_accepted:
            serializer = TicketLabelSuggestionSerializer(suggestion)
            return Response({"detail": "La sugerencia ya estaba aceptada.", "suggestion": serializer.data})

        label = accept_ticket_label_suggestion(suggestion, actor=request.user)
        suggestion.refresh_from_db()
        logger.info(
            "Sugerencia aceptada",
            extra={"ticket_id": ticket.id, "suggestion_id": suggestion.id, "actor_id": request.user.id},
        )

        return Response(
            {
                "detail": "Etiqueta confirmada.",
                "suggestion": TicketLabelSuggestionSerializer(suggestion).data,
                "label": TicketLabelSerializer(label).data,
            },
            status=status.HTTP_200_OK,
        )

    # ---------- H5: Transiciones ----------
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """
        Cambiar estado:
          OPEN -> IN_PROGRESS
          IN_PROGRESS -> RESOLVED | OPEN
          RESOLVED -> CLOSED | IN_PROGRESS
          CLOSED -> (no avanza)
        Permisos: ADMINISTRADOR o TECNICO asignado.
        Efectos: setea resolved_at/closed_at, comentario opcional, AuditLog 'STATUS'.
        """
        ticket = self.get_object()
        u = request.user

        next_status = request.data.get("next_status")
        comment = request.data.get("comment", "")
        is_internal = bool(request.data.get("internal", False))

        allowed = {
            Ticket.OPEN: {Ticket.IN_PROGRESS},
            Ticket.IN_PROGRESS: {Ticket.RESOLVED, Ticket.OPEN},
            Ticket.RESOLVED: {Ticket.CLOSED, Ticket.IN_PROGRESS},
            Ticket.CLOSED: set(),
        }

        if next_status not in dict(Ticket.STATUS_CHOICES):
            return Response({"detail": "Estado destino inválido"}, status=400)

        if next_status not in allowed.get(ticket.status, set()):
            return Response({"detail": f"Transición no permitida desde {ticket.status} → {next_status}"}, status=400)

        if not (is_admin(u) or (is_tech(u) and ticket.assigned_to_id == u.id)):
            return Response({"detail": "No autorizado a cambiar estado"}, status=403)

        previous_status = ticket.status
        status_map = dict(Ticket.STATUS_CHOICES)
        ticket._status_changed_by = u
        ticket._skip_status_signal_audit = True
        ticket.status = next_status
        if next_status == Ticket.RESOLVED:
            ticket.resolved_at = timezone.now()
        if next_status == Ticket.CLOSED:
            ticket.closed_at = timezone.now()
        ticket.save()

        comment_obj = None
        comment_clean = sanitize_text(comment)
        if comment_clean:
            comment_obj = TicketComment.objects.create(
                ticket=ticket, author=u, body=comment_clean, is_internal=is_internal
            )

        AuditLog.objects.create(
            ticket=ticket, actor=u, action="STATUS",
            meta={
                "from": previous_status,
                "from_label": status_map.get(previous_status),
                "to": next_status,
                "to_label": status_map.get(next_status),
                "with_comment": bool(comment_clean),
                "internal": bool(is_internal),
                "comment_id": getattr(comment_obj, "id", None),
                "body_preview": comment_obj.body[:120] if comment_obj else "",
            },
        )

        return Response({"message": "Estado actualizado", "status": next_status}, status=200)

    # ---------- Comentarios (GET/POST) ----------
    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        """
        GET: lista comentarios del ticket (oculta internos a SOLICITANTE).
        POST: crea comentario (SOLICITANTE siempre público). AuditLog 'COMMENT'.
        """
        ticket = self.get_object()
        u = request.user

        if request.method == "GET":
            qs = TicketComment.objects.filter(ticket=ticket).order_by("created_at")
            if not (is_admin(u) or is_tech(u)):  # solicitante -> no ve internos
                qs = qs.filter(is_internal=False)
            ser = TicketCommentSerializer(qs, many=True)
            return Response(ser.data)

        # POST
        data = request.data.copy()
        data["ticket"] = ticket.id
        if not (is_admin(u) or is_tech(u)):  # solicitante no puede marcar interno
            data["is_internal"] = False

        ser = TicketCommentSerializer(data=data, context={"request": request})
        ser.is_valid(raise_exception=True)
        comment = ser.save()  # author se resuelve en el serializer (HiddenField)

        AuditLog.objects.create(
            ticket=ticket,
            actor=request.user,
            action="COMMENT",
            meta={
                "internal": bool(ser.validated_data.get("is_internal", False)),
                "comment_id": comment.id,
                "with_attachment": False,
                "body_preview": comment.body[:120],
            },
        )
        return Response(TicketCommentSerializer(comment).data, status=201)

    # ---------- Adjuntos (GET lista / POST subir) ----------
    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser, FormParser])
    def attachments(self, request, pk=None):
        """
        GET: lista adjuntos del ticket.
        POST: sube un archivo (multipart/form-data).
        Permisos para ambos:
          - ADMINISTRADOR
          - TECNICO (si asignado o sin asignación)
          - SOLICITANTE dueño del ticket
        AuditLog 'ATTACH' en POST.
        """
        ticket = self.get_object()
        u = request.user

        # Permisos base (ver/subir adjuntos)
        allowed = (
            is_admin(u) or
            (is_tech(u) and ticket.assigned_to_id in (None, u.id)) or
            (ticket.requester_id == u.id)
        )
        if not allowed:
            return Response({"detail": "No autorizado a ver/adjuntar"}, status=403)

        if request.method == "GET":
            qs = TicketAttachment.objects.filter(ticket=ticket).order_by("-uploaded_at")
            data = TicketAttachmentSerializer(qs, many=True).data
            return Response(data, status=200)

        # POST (subida)
        if "file" not in request.FILES:
            return Response({"detail": "Archivo 'file' requerido"}, status=400)

        f = request.FILES["file"]

        try:
            validate_upload(f)
        except UploadValidationError as e:
            return Response({"detail": str(e)}, status=400)

        content_type = getattr(f, "content_type", "") or ""

        # --- Crear registro ---
        att = TicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=u,
            file=f,
            content_type=content_type,
            size=f.size,
        )

        AuditLog.objects.create(
            ticket=ticket,
            actor=u,
            action="ATTACH",
            meta={
                "filename": att.file.name.rsplit("/", 1)[-1],
                "size": att.size,
                "content_type": att.content_type,
            },
        )

        return Response(TicketAttachmentSerializer(att).data, status=201)


    # ---------- Historial de asignaciones (GET) ----------
    @action(detail=True, methods=["get"])
    def assignments(self, request, pk=None):
        """
        GET /api/tickets/{id}/assignments/
        Devuelve el historial de asignaciones del ticket (últimos primero).
        Visible si puedes ver el ticket (mismas reglas de get_queryset()).
        """
        ticket = self.get_object()  # respeta permisos de visibilidad
        qs = ticket.assignments.select_related("from_user", "to_user").order_by("-created_at")
        data = TicketAssignmentSerializer(qs, many=True).data
        return Response(data, status=200)

    # ---------- Audit log (GET) ----------
    @action(detail=True, methods=["get"])
    def audit(self, request, pk=None):
        """
        GET /api/tickets/{id}/audit/
        Devuelve el historial (AuditLog) del ticket, del más nuevo al más antiguo.
        """
        ticket = self.get_object()  # respeta permisos/visibilidad
        logs = ticket.audit_logs.select_related("actor").values(
            "action",           # CREATE, ASSIGN, STATUS, COMMENT, ATTACH
            "actor__username",  # quién ejecutó
            "meta",             # datos extra
            "created_at",       # cuándo
        ).order_by("-created_at")
        return Response(list(logs), status=200)




class TicketSuggestionBulkRecomputeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not is_admin(request.user):
            return Response(
                {"detail": "Solo administradores pueden recalcular en lote."},
                status=status.HTTP_403_FORBIDDEN,
            )

        raw_ticket_ids = request.data.get("ticket_ids") or []
        if isinstance(raw_ticket_ids, (int, str)):
            raw_ticket_ids = [raw_ticket_ids]

        try:
            ticket_ids = [int(value) for value in raw_ticket_ids]
        except (TypeError, ValueError):
            return Response(
                {"detail": "ticket_ids debe ser una lista de enteros."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        threshold = request.data.get("threshold")
        parsed_threshold = None
        if threshold is not None:
            try:
                parsed_threshold = float(threshold)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "threshold debe ser numérico."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not (0 <= parsed_threshold <= 1):
                return Response(
                    {"detail": "threshold debe estar entre 0 y 1."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        only_open = bool(request.data.get("only_open", False))

        limit_raw = request.data.get("limit")
        if limit_raw is not None:
            try:
                limit = int(limit_raw)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "limit debe ser entero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if limit <= 0:
                return Response(
                    {"detail": "limit debe ser mayor a cero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            limit = None

        chunk_raw = request.data.get("chunk_size")
        if chunk_raw is not None:
            try:
                chunk_size = int(chunk_raw)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "chunk_size debe ser entero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            chunk_size = 200

        qs = Ticket.objects.select_related("priority", "area", "category").order_by("id")
        if only_open:
            qs = qs.filter(status__in=[Ticket.OPEN, Ticket.IN_PROGRESS])
        if ticket_ids:
            qs = qs.filter(id__in=set(ticket_ids))
        if limit is not None:
            qs = qs[:limit]

        metrics = bulk_recompute_ticket_label_suggestions(
            queryset=qs,
            threshold=parsed_threshold,
            chunk_size=chunk_size,
        )

        logger.info(
            "Recomputo masivo de sugerencias",
            extra={"actor_id": request.user.id, "metrics": metrics},
        )

        return Response(
            {
                "detail": "Recomputo completado.",
                "metrics": metrics,
            },
            status=status.HTTP_200_OK,
        )


class TicketClusterRetrainView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not is_admin(request.user):
            return Response(
                {"detail": "Solo administradores pueden reentrenar clústeres."},
                status=status.HTTP_403_FORBIDDEN,
            )

        raw_clusters = request.data.get("clusters", 5)
        try:
            clusters = int(raw_clusters)
        except (TypeError, ValueError):
            return Response(
                {"detail": "clusters debe ser un entero mayor a cero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if clusters <= 0:
            return Response(
                {"detail": "clusters debe ser un entero mayor a cero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start = time.perf_counter()
            summary = train_ticket_clusters(num_clusters=clusters)
            duration = round(time.perf_counter() - start, 4)
        except RuntimeError as exc:
            logger.exception(
                "Error reentrenando clústeres", extra={"actor_id": request.user.id}
            )
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        metrics = {
            "total_tickets": summary.total_tickets,
            "requested_clusters": summary.requested_clusters,
            "effective_clusters": summary.effective_clusters,
            "assignments": summary.assignments,
            "duration_seconds": duration,
        }

        logger.info(
            "Reentrenamiento de clústeres vía API",
            extra={"actor_id": request.user.id, "metrics": metrics},
        )

        return Response(
            {
                "detail": "Clusterización completada.",
                "metrics": metrics,
            },
            status=status.HTTP_200_OK,
        )


class TicketAlertListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = TicketAlertPagination

    def get(self, request):
        raw_warn_ratio = request.query_params.get("warn_ratio")
        try:
            warn_ratio = float(raw_warn_ratio) if raw_warn_ratio is not None else 0.8
        except (TypeError, ValueError):
            return Response(
                {"detail": "warn_ratio debe ser numérico."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if warn_ratio <= 0 or warn_ratio > 1:
            return Response(
                {"detail": "warn_ratio debe estar en el rango (0, 1]."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        severity_filter = (request.query_params.get("severity") or "").lower()

        base_qs = Ticket.objects.select_related(
            "priority", "assigned_to", "requester"
        ).filter(status__in=[Ticket.OPEN, Ticket.IN_PROGRESS])
        base_qs = filter_tickets_for_user(base_qs, request.user)

        snapshots = collect_ticket_alerts(base_qs, warn_ratio=warn_ratio)

        results = []
        for snapshot in snapshots:
            severity = snapshot.severity
            if severity_filter and severity != severity_filter:
                continue

            ticket = snapshot.ticket
            results.append(
                {
                    "ticket": {
                        "id": ticket.id,
                        "code": ticket.code,
                        "title": ticket.title,
                        "status": ticket.status,
                        "priority": {
                            "id": ticket.priority_id,
                            "name": getattr(ticket.priority, "name", None),
                        },
                        "assigned_to": (
                            {
                                "id": ticket.assigned_to_id,
                                "username": getattr(ticket.assigned_to, "username", None),
                            }
                            if ticket.assigned_to_id
                            else None
                        ),
                    },
                    "sla": {
                        "severity": severity,
                        "due_at": snapshot.due_at,
                        "remaining_hours": round(snapshot.remaining_hours, 2),
                        "elapsed_hours": round(snapshot.elapsed_hours, 2),
                        "threshold_hours": round(snapshot.threshold_hours, 2),
                    },
                }
            )

        ordering = request.query_params.get("ordering", "due_at")
        reverse = ordering.startswith("-")
        key = ordering.lstrip("-")

        if key == "remaining_hours":
            results.sort(
                key=lambda item: item["sla"]["remaining_hours"], reverse=reverse
            )
        else:
            results.sort(key=lambda item: item["sla"]["due_at"], reverse=reverse)

        warnings_count = sum(
            1 for item in results if item["sla"]["severity"] == "warning"
        )
        breaches_count = sum(
            1 for item in results if item["sla"]["severity"] == "breach"
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(results, request, view=self)
        response = paginator.get_paginated_response(page)
        response.data["summary"] = {
            "warn_ratio": warn_ratio,
            "warnings": warnings_count,
            "breaches": breaches_count,
        }

        return response
