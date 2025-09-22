# accounts/management/commands/init_rbac.py
"""Comando utilitario para inicializar los roles base del sistema."""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from tickets.models import Ticket, TicketComment, TicketAttachment
from catalog.models import Category, Priority, Area
from accounts.roles import ROLE_ADMIN, ROLE_TECH, ROLE_REQUESTER


class Command(BaseCommand):
    """Crea (o actualiza) los grupos principales con los permisos esperados."""

    help = (
        "Inicializa grupos y asigna permisos por defecto para solicitantes, "
        "técnicos y administradores."
    )

    def handle(self, *args, **kwargs):
        """Entrypoint del comando ``init_rbac``."""

        def std_perms(model):
            """
            Devuelve los permisos CRUD estándar (add/change/view/delete) para un modelo.

            Mantener esta lógica centralizada evita olvidarnos de registrar alguno
            al incorporar nuevos catálogos.
            """

            content_type = ContentType.objects.get_for_model(model)
            codes = [f"{action}_{model._meta.model_name}" for action in ("add", "change", "view", "delete")]
            return list(
                Permission.objects.filter(content_type=content_type, codename__in=codes)
            )

        # Permisos personalizados definidos en tickets/models.py (Meta.permissions)
        custom_codes = [
            "assign_ticket",
            "transition_ticket",
            "comment_internal",
            "view_all_tickets",
        ]
        custom_perms = list(Permission.objects.filter(codename__in=custom_codes))

        # Aseguramos que existan los tres grupos principales
        requester_group, _ = Group.objects.get_or_create(name=ROLE_REQUESTER)
        tech_group, _ = Group.objects.get_or_create(name=ROLE_TECH)
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)

        # Catálogos: categorías, prioridades y áreas
        catalog_perms = std_perms(Category) + std_perms(Priority) + std_perms(Area)

        # Tickets y entidades relacionadas
        ticket_perms = std_perms(Ticket) + custom_perms
        comment_perms = std_perms(TicketComment)
        attachment_perms = std_perms(TicketAttachment)

        # --- Permisos por rol ---
        requester_group.permissions.set(
            [
                # Puede crear y consultar sus propios tickets
                *[
                    perm
                    for perm in ticket_perms
                    if perm.codename in ("add_ticket", "view_ticket")
                ],
                # Puede agregar y ver comentarios
                *[
                    perm
                    for perm in comment_perms
                    if perm.codename.startswith(("add_", "view_"))
                ],
                # Puede adjuntar evidencia y consultarla
                *[
                    perm
                    for perm in attachment_perms
                    if perm.codename.startswith(("add_", "view_"))
                ],
            ]
        )

        tech_group.permissions.set(
            [
                # Puede ver todos los tickets, actualizarlos y moverlos de estado
                *[
                    perm
                    for perm in ticket_perms
                    if perm.codename
                    in (
                        "view_ticket",
                        "change_ticket",
                        "transition_ticket",
                        "view_all_tickets",
                    )
                ],
                # Gestionar comentarios (crear, ver y editar los suyos)
                *[
                    perm
                    for perm in comment_perms
                    if perm.codename.startswith(("add_", "view_", "change_"))
                ],
                # Adjuntar o revisar archivos vinculados al ticket
                *[
                    perm
                    for perm in attachment_perms
                    if perm.codename.startswith(("add_", "view_"))
                ],
            ]
        )

        # El rol administrador recibe el set completo de permisos
        admin_group.permissions.set(
            catalog_perms + ticket_perms + comment_perms + attachment_perms
        )

        self.stdout.write(self.style.SUCCESS("RBAC inicializado"))
