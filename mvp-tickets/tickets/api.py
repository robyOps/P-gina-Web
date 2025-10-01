# tickets/api.py

# ------------------------- IMPORTS -------------------------
from django.utils import timezone  # para sellos de tiempo (resolved_at / closed_at)
from django.contrib.auth import get_user_model  # para obtener el modelo de usuario (custom o por defecto)

# DRF: vistas, permisos, decoradores para acciones custom, respuesta y parsers de archivos
from rest_framework import viewsets, permissions
from rest_framework.decorators import action  # define endpoints como /assign, /transition, etc.
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser  # subir archivos (multipart/form-data)

# Modelos (incluye AuditLog para trazabilidad)
from .models import (
    Ticket,              # entidad principal
    TicketComment,       # comentarios (internos/públicos)
    TicketAttachment,    # adjuntos
    TicketAssignment,    # historial de asignaciones
    AuditLog,            # historial/auditoría de acciones
)

# Serializers (modelos <-> JSON)
from .serializers import (
    TicketSerializer,
    TicketCommentSerializer,
    TicketAttachmentSerializer,
    TicketAssignmentSerializer,  # útil para exponer historial de asignaciones
)

# Validación de archivos subidos
from .validators import validate_upload, UploadValidationError

from .services import apply_auto_assign
import logging

logger = logging.getLogger(__name__)

# Modelo de usuario activo
User = get_user_model()

# Helpers de roles
from accounts.roles import is_admin, is_tech, ROLE_ADMIN, ROLE_TECH


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

    # Query base (con relaciones) y orden (últimos creados primero)
    queryset = (
        Ticket.objects.select_related(
            "category", "priority", "area", "requester", "assigned_to"
        ).order_by("-created_at")
    )

    # Filtros por query string (?status=&category=&priority=&area=)
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
        reason = request.data.get("reason", "")

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
        if comment:
            comment_obj = TicketComment.objects.create(
                ticket=ticket, author=u, body=comment, is_internal=is_internal
            )

        AuditLog.objects.create(
            ticket=ticket, actor=u, action="STATUS",
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


