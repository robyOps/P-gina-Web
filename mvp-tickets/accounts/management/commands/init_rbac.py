# accounts/management/commands/init_rbac.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from tickets.models import Ticket, TicketComment, TicketAttachment
from catalog.models import Category, Priority, Area

class Command(BaseCommand):
    help = "Inicializa grupos y asigna permisos por defecto"

    def handle(self, *args, **kwargs):
        def std_perms(model):
            ct = ContentType.objects.get_for_model(model)
            codes = [f"{c}_{model._meta.model_name}" for c in ("add","change","view","delete")]
            return list(Permission.objects.filter(content_type=ct, codename__in=codes))

        custom_codes = ["assign_ticket", "transition_ticket", "comment_internal", "view_all_tickets"]
        custom = list(Permission.objects.filter(codename__in=custom_codes))

        requester, _ = Group.objects.get_or_create(name="REQUESTER")
        tech, _ = Group.objects.get_or_create(name="TECH")
        admin, _ = Group.objects.get_or_create(name="ADMIN")

        cat_perms = std_perms(Category) + std_perms(Priority) + std_perms(Area)
        t_perms   = std_perms(Ticket) + custom
        tc_perms  = std_perms(TicketComment)
        ta_perms  = std_perms(TicketAttachment)

        requester.permissions.set([
            *[p for p in t_perms if p.codename in ("add_ticket","view_ticket")],
            *[p for p in tc_perms if p.codename.startswith(("add_","view_"))],
            *[p for p in ta_perms if p.codename.startswith(("add_","view_"))],
        ])

        tech.permissions.set([
            *[p for p in t_perms if p.codename in ("view_ticket","change_ticket","transition_ticket")],
            *[p for p in tc_perms if p.codename.startswith(("add_","view_","change_"))],
            *[p for p in ta_perms if p.codename.startswith(("add_","view_"))],
        ])

        admin.permissions.set(cat_perms + t_perms + tc_perms + ta_perms)
        self.stdout.write(self.style.SUCCESS("RBAC inicializado"))
