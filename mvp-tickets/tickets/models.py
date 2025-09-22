# tickets/models.py

# ------------------------- IMPORTS -------------------------
from django.db import models                     # tipos de campo y utilidades de modelos
from django.conf import settings                 # para referenciar al modelo de usuario activo (AUTH_USER_MODEL)
from catalog.models import Category, Priority, Area  # catálogos externos (llaves foráneas)
from django.core.exceptions import ValidationError
import uuid

# Para cálculo de SLA y tiempos
from datetime import timedelta
from django.utils import timezone


# ------------------------- TICKET -------------------------
class Ticket(models.Model):
    # Estados como constantes (evita typos y facilita comparar)
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    # Lista de opciones de estado (clave, etiqueta legible)
    STATUS_CHOICES = [
        (OPEN, "Abierto"),
        (IN_PROGRESS, "En Progreso"),
        (RESOLVED, "Resuelto"),
        (CLOSED, "Cerrado"),
    ]

    INCIDENT = "INCIDENT"
    REQUEST = "REQUEST"
    KIND_CHOICES = [
        (INCIDENT, "Incidente"),
        (REQUEST, "Solicitud"),
    ]

    # Código legible del ticket (único). Ej: TCK-AB12CD34
    code = models.CharField(max_length=20, unique=True)

    # Campos básicos: título y descripción
    title = models.CharField(max_length=200)
    description = models.TextField()

    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default=REQUEST,
        help_text="Clasificación funcional del ticket (incidente o solicitud)",
    )

    # Quién solicitó (usuario autenticado) -> si se borra el usuario, se borran sus tickets (CASCADE)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets"
    )

    # Catálogo: categoría / prioridad (protegidos: no se pueden borrar si hay tickets apuntando)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    priority = models.ForeignKey(Priority, on_delete=models.PROTECT)

    # Área (opcional). PROTECT para no borrar áreas en uso
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True)

    # Estado del ticket con choices y default
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)

    # Técnico asignado (opcional). Si el técnico se borra, dejamos NULL (SET_NULL)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned",
    )

    # Timestamps de ciclo de vida
    created_at = models.DateTimeField(auto_now_add=True)  # se fija al crear
    updated_at = models.DateTimeField(auto_now=True)      # se actualiza en cada save()
    resolved_at = models.DateTimeField(null=True, blank=True)  # cuando pasa a RESOLVED
    closed_at = models.DateTimeField(null=True, blank=True)    # cuando pasa a CLOSED

    class Meta:
        # Permisos a nivel de objeto/app (opcionales para usar con @permission_required o permisos custom)
        permissions = [
            ("assign_ticket", "Puede asignar ticket"),
            ("transition_ticket", "Puede cambiar estado de ticket"),
            ("comment_internal", "Puede comentar internamente"),
            ("view_all_tickets", "Puede ver todos los tickets"),
        ]

    def __str__(self):
        # Representación legible en admin/shell
        return f"{self.code} — {self.title}"

    def save(self, *args, **kwargs):
        """Genera un código secuencial basado en el ID primario."""
        creating = self.pk is None
        if creating and not self.code:
            # Evita colisiones con el unique index usando un valor temporal único
            self.code = f"_TMP-{uuid.uuid4().hex}"

        super().save(*args, **kwargs)

        if creating:
            desired = str(self.pk)
            if self.code != desired:
                type(self).objects.filter(pk=self.pk).update(code=desired)
                self.code = desired

    # ------------------------- SLA (helpers) -------------------------
    @property
    def sla_hours_value(self) -> int:
        """
        Horas de SLA según la prioridad (si no existe el campo, usa 72 por defecto).
        """
        try:
            return int(getattr(self.priority, "sla_hours", 72) or 72)
        except Exception:
            return 72

    @property
    def due_at(self):
        """
        Fecha/hora en la que vence el SLA (created_at + sla_hours).
        """
        return self.created_at + timedelta(hours=self.sla_hours_value)

    @property
    def remaining_hours(self) -> float:
        """
        Horas restantes para que venza el SLA (negativo si ya venció).
        """
        return (self.due_at - timezone.now()).total_seconds() / 3600.0

    @property
    def is_overdue(self) -> bool:
        """
        True si el SLA está vencido y el ticket sigue en OPEN/IN_PROGRESS.
        """
        return self.status in (self.OPEN, self.IN_PROGRESS) and self.remaining_hours < 0

    @property
    def is_warning(self) -> bool:
        """
        True si está en el último 20% del tiempo antes de vencer (warning).
        """
        return (
            self.status in (self.OPEN, self.IN_PROGRESS)
            and 0 <= self.remaining_hours <= (0.2 * self.sla_hours_value)
        )

    @property
    def is_critical(self) -> bool:
        """
        True si la prioridad es CRITICAL (para mostrar badge rojo en UI).
        """
        return (getattr(self.priority, "name", "") or "").lower() == "crítica"


# ------------------------- COMENTARIOS -------------------------
class TicketComment(models.Model):
    # A qué ticket pertenece el comentario
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)

    # Autor del comentario
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Texto y si es interno (visible solo a TECNICO/ADMINISTRADOR)
    body = models.TextField()
    is_internal = models.BooleanField(default=False)

    # Cuándo se creó
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Primeros 40 chars para mostrar algo legible
        return f"Comment({self.ticket.code}) by {self.author}: {self.body[:40]}"


# ------------------------- ADJUNTOS -------------------------
class TicketAttachment(models.Model):
    # Ticket al que se adjunta
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)

    # Quién subió el archivo
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Archivo físico. La ruta incluye año/mes para organizar
    file = models.FileField(upload_to="attachments/%Y/%m/")

    # Metadatos útiles del archivo
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)

    # Cuándo se subió
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment({self.ticket.code}) {self.file.name}"


# ------------------------- ASIGNACIONES (historial) -------------------------
class TicketAssignment(models.Model):
    # Ticket involucrado
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="assignments"
    )

    # Quién ejecutó la asignación (puede quedar NULL si el usuario fue borrado)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_made",
    )

    # A quién se asignó (requerido)
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments_received"
    )

    # Motivo de la asignación (texto corto opcional)
    reason = models.CharField(max_length=255, blank=True)

    # Cuándo se hizo la asignación
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Assign({self.ticket.code}) -> {getattr(self.to_user, 'username', '?')}"


# ------------------------- AUDITORÍA (eventos) -------------------------
class AuditLog(models.Model):
    # Tipos de eventos que registramos para trazabilidad
    ACTION_CHOICES = [
        ("CREATE", "Create Ticket"),
        ("ASSIGN", "Assign/Reassign"),
        ("STATUS", "Change Status"),
        ("COMMENT", "Comment"),
        ("ATTACH", "Attachment"),
        ("SLA_WARN", "SLA Warning"),   # nuevo: advertencia SLA
        ("SLA_BREACH", "SLA Breach"),  # nuevo: SLA vencido
    ]

    # Ticket al que pertenece el evento
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="audit_logs"
    )

    # Usuario que ejecutó la acción (puede quedar NULL si se borró)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    # Tipo de acción (choices)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    # Información adicional (flexible): ids, motivo, filename, etc.
    meta = models.JSONField(default=dict, blank=True)

    # Cuándo ocurrió el evento
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Orden por defecto: últimos eventos primero
        ordering = ["-created_at"]

    def __str__(self):
        return f"Audit({self.ticket.code}) {self.action}"


class EventLog(models.Model):
    """Registro global de eventos para auditoría mínima."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    model = models.CharField(max_length=50)
    obj_id = models.PositiveIntegerField()
    action = models.CharField(max_length=50)
    message = models.CharField(max_length=255)
    resource_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Event({self.model}:{self.obj_id}) {self.action}"

class AutoAssignRule(models.Model):
    """Regla: (category y/o area) -> técnico."""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.CASCADE, null=True, blank=True)
    tech = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auto_rules")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["category", "area"], name="uniq_auto_rule_cat_area")
        ]

    def __str__(self):
        parts = []
        if self.category_id: parts.append(f"cat={self.category.name}")
        if self.area_id: parts.append(f"area={self.area.name}")
        return f"Rule({', '.join(parts) or 'default'}) -> {getattr(self.tech,'username','?')}"


# ------------------------- NOTIFICACIONES -------------------------
class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notif({self.user_id}) {self.message[:20]}"


class FAQ(models.Model):
    """Entradas de preguntas frecuentes administradas por técnicos y administradores."""

    question = models.CharField(max_length=255)
    answer = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="faqs_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faqs_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question"]

    def __str__(self):
        return self.question
