from django.conf import settings
from django.db import models


class CatalogCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField()
    is_active = models.BooleanField()

    class Meta:
        db_table = 'catalog_category'


class CatalogPriority(models.Model):
    id = models.BigAutoField(primary_key=True)
    sla_hours = models.PositiveIntegerField()
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = 'catalog_priority'


class CatalogArea(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120, unique=True)
    is_critical = models.BooleanField()

    class Meta:
        db_table = 'catalog_area'


class CatalogSubcategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField()
    is_active = models.BooleanField()
    category = models.ForeignKey(
        CatalogCategory,
        on_delete=models.PROTECT,
        related_name='subcategories',
    )

    class Meta:
        db_table = 'catalog_subcategory'
        unique_together = (('category', 'name'),)


class AccountsUserProfile(models.Model):
    id = models.BigAutoField(primary_key=True)
    rut = models.CharField(max_length=12, unique=True, blank=True, null=True)
    area = models.ForeignKey(
        CatalogArea,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='user_profiles',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    is_critical_actor = models.BooleanField()

    class Meta:
        db_table = 'accounts_userprofile'


class TicketsTicket(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20)
    updated_at = models.DateTimeField()
    resolved_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    area = models.ForeignKey(
        CatalogArea,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='tickets',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='assigned_tickets',
    )
    category = models.ForeignKey(
        CatalogCategory,
        on_delete=models.PROTECT,
        related_name='tickets',
    )
    priority = models.ForeignKey(
        CatalogPriority,
        on_delete=models.PROTECT,
        related_name='tickets',
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='requested_tickets',
    )
    kind = models.CharField(max_length=20)
    cluster_id = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField()
    subcategory = models.ForeignKey(
        CatalogSubcategory,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='tickets',
    )

    class Meta:
        db_table = 'tickets_ticket'


class TicketsAuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    action = models.CharField(max_length=20)
    meta = models.JSONField()
    created_at = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='ticket_audit_logs',
    )
    ticket = models.ForeignKey(
        TicketsTicket,
        on_delete=models.CASCADE,
        related_name='audit_logs',
    )

    class Meta:
        db_table = 'tickets_auditlog'


class TicketsAutoAssignRule(models.Model):
    id = models.BigAutoField(primary_key=True)
    is_active = models.BooleanField()
    created_at = models.DateTimeField()
    area = models.ForeignKey(
        CatalogArea,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='auto_assign_rules',
    )
    category = models.ForeignKey(
        CatalogCategory,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='auto_assign_rules',
    )
    tech = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='auto_assign_rules',
    )
    subcategory = models.ForeignKey(
        CatalogSubcategory,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='auto_assign_rules',
    )

    class Meta:
        db_table = 'tickets_autoassignrule'
        unique_together = (('category', 'subcategory', 'area'),)


class TicketsEventLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    model = models.CharField(max_length=50)
    obj_id = models.PositiveIntegerField()
    action = models.CharField(max_length=50)
    message = models.CharField(max_length=255)
    resource_id = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='ticket_event_logs',
    )

    class Meta:
        db_table = 'tickets_eventlog'


class TicketsFaq(models.Model):
    id = models.BigAutoField(primary_key=True)
    question = models.CharField(max_length=255)
    answer = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_faqs',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='updated_faqs',
    )
    category = models.ForeignKey(
        CatalogCategory,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='faqs',
    )
    subcategory = models.ForeignKey(
        CatalogSubcategory,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='faqs',
    )
    image = models.ImageField(max_length=100, blank=True, null=True)
    video_file = models.FileField(max_length=100, blank=True, null=True)
    video_url = models.URLField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = 'tickets_faq'


class TicketsNotification(models.Model):
    id = models.BigAutoField(primary_key=True)
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    is_read = models.BooleanField()
    created_at = models.DateTimeField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='notifications',
    )

    class Meta:
        db_table = 'tickets_notification'


class TicketsTicketAssignment(models.Model):
    id = models.BigAutoField(primary_key=True)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField()
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='ticket_assignments_from',
    )
    ticket = models.ForeignKey(
        TicketsTicket,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ticket_assignments_to',
    )

    class Meta:
        db_table = 'tickets_ticketassignment'


class TicketsTicketAttachment(models.Model):
    id = models.BigAutoField(primary_key=True)
    file = models.FileField(max_length=100)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField()
    ticket = models.ForeignKey(
        TicketsTicket,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ticket_attachments',
    )

    class Meta:
        db_table = 'tickets_ticketattachment'


class TicketsTicketComment(models.Model):
    id = models.BigAutoField(primary_key=True)
    body = models.TextField()
    is_internal = models.BooleanField()
    created_at = models.DateTimeField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ticket_comments',
    )
    ticket = models.ForeignKey(
        TicketsTicket,
        on_delete=models.CASCADE,
        related_name='comments',
    )

    class Meta:
        db_table = 'tickets_ticketcomment'
