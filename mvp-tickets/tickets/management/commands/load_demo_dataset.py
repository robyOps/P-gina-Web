"""
Crea un dataset de demostración rico en tickets, catálogos, usuarios y reglas.

- Ejecuta ``python manage.py load_demo_dataset --purge`` para borrar datos previos
  (tickets, catálogos demo y usuarios de prueba) y volver a generar todo.
- Genera por defecto 500 tickets variados con categorías, subcategorías,
  prioridades, áreas, FAQs y reglas de autoasignación activas.
"""

from __future__ import annotations

import random
from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.roles import ROLE_ADMIN, ROLE_REQUESTER, ROLE_TECH
from catalog.models import Area, Category, Priority, Subcategory
from tickets.models import AutoAssignRule, FAQ, Ticket
from tickets.services import apply_auto_assign

User = get_user_model()


class Command(BaseCommand):
    help = "Carga un dataset de demostración con catálogos, usuarios y tickets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tickets",
            type=int,
            default=500,
            help="Cantidad de tickets a generar (por defecto: 500).",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Elimina tickets, catálogos demo, FAQs y usuarios de prueba antes de crear el dataset.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        total_tickets = options["tickets"]
        purge = options["purge"]

        random.seed(202501)

        self.stdout.write(self.style.WARNING("Inicializando grupos y permisos base (init_rbac)..."))
        call_command("init_rbac")

        if purge:
            self._purge_demo_data()

        priorities = self._create_priorities()
        areas = self._create_areas()
        categories = self._create_categories()
        techs, requesters, admins = self._create_users(areas)

        self._create_autoassign_rules(categories, areas, techs)
        self._create_faqs(categories, requesters[0])

        status_plan = self._build_status_plan(total_tickets)
        counts = Counter(status_plan)
        tickets = self._create_tickets(
            status_plan=status_plan,
            priorities=priorities,
            areas=areas,
            categories=categories,
            requesters=requesters,
        )

        self.stdout.write(self.style.SUCCESS("Dataset demo generado con éxito"))
        self.stdout.write(
            self.style.NOTICE(
                f"Tickets generados: {len(tickets)} | Abiertos: {counts[Ticket.OPEN]} | "
                f"En progreso: {counts[Ticket.IN_PROGRESS]} | Resueltos: {counts[Ticket.RESOLVED]} | "
                f"Cerrados: {counts[Ticket.CLOSED]}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Usuarios demo creados (password: Demo1234!): "
                "admin_ana, admin_bruno, tech_ale, tech_beto, req_camila, req_diego"
            )
        )

    # ------------------------------------------------------------------
    # Catálogos
    # ------------------------------------------------------------------
    def _create_priorities(self):
        data = [
            ("BAJA", 120),
            ("MEDIA", 72),
            ("ALTA", 48),
            ("CRÍTICA", 8),
        ]
        priorities = []
        for name, hours in data:
            obj, _ = Priority.objects.update_or_create(name=name, defaults={"sla_hours": hours})
            priorities.append(obj)
        return priorities

    def _create_areas(self):
        data = [
            ("OPERACIONES", False),
            ("TECNOLOGÍA", False),
            ("DIRECCIÓN EJECUTIVA", True),
            ("FINANZAS", False),
            ("EXPERIENCIA CLIENTE", True),
        ]
        areas = []
        for name, is_critical in data:
            obj, _ = Area.objects.update_or_create(name=name, defaults={"is_critical": is_critical})
            areas.append(obj)
        return areas

    def _create_categories(self):
        data = [
            ("SOPORTE APLICACIONES", ["ERP", "CRM", "PAGOS"], "Fallos funcionales y mejoras en sistemas de negocio."),
            ("INFRAESTRUCTURA", ["VPN", "WIFI", "CORREO"], "Redes, accesos y servicios de conectividad."),
            ("SEGURIDAD", ["CREDENCIALES", "MFA", "ALERTAS SIEM"], "Gestión de identidades y alertas"),
            ("DISPOSITIVOS", ["LAPTOP", "IMPRESORA", "PERIFÉRICOS"], "Hardware de usuario final"),
        ]
        categories = []
        for name, subs, description in data:
            cat, _ = Category.objects.update_or_create(
                name=name, defaults={"description": description, "is_active": True}
            )
            categories.append(cat)
            for sub in subs:
                Subcategory.objects.update_or_create(
                    category=cat, name=sub, defaults={"description": f"Subcategoría {sub.title()}"}
                )
        return categories

    # ------------------------------------------------------------------
    # Usuarios
    # ------------------------------------------------------------------
    def _create_users(self, areas):
        admin_group = Group.objects.get(name=ROLE_ADMIN)
        tech_group = Group.objects.get(name=ROLE_TECH)
        requester_group = Group.objects.get(name=ROLE_REQUESTER)

        demo_password = "Demo1234!"
        area_lookup = {
            "OPERACIONES": None,
            "TECNOLOGÍA": None,
            "DIRECCIÓN EJECUTIVA": None,
            "FINANZAS": None,
            "EXPERIENCIA CLIENTE": None,
        }
        for area in areas:
            if area.name in area_lookup:
                area_lookup[area.name] = area

        def build_user(username, first, last, group: Group, is_staff=False, is_critical=False, area=None):
            User.objects.filter(username=username).delete()
            user = User.objects.create_user(
                username=username,
                email=f"{username}@demo.local",
                password=demo_password,
                first_name=first,
                last_name=last,
                is_staff=is_staff,
            )
            user.groups.add(group)
            profile = getattr(user, "profile", None)
            if profile:
                profile.area = area
                profile.is_critical_actor = is_critical
                profile.save(update_fields=["area", "is_critical_actor"])
            return user

        admins = [
            build_user("admin_ana", "Ana", "Pérez", admin_group, is_staff=True, area=area_lookup["DIRECCIÓN EJECUTIVA"]),
            build_user("admin_bruno", "Bruno", "Salas", admin_group, is_staff=True, area=area_lookup["TECNOLOGÍA"]),
        ]
        techs = [
            build_user("tech_ale", "Ale", "Valdés", tech_group, area=area_lookup["TECNOLOGÍA"]),
            build_user(
                "tech_beto",
                "Beto",
                "Ramos",
                tech_group,
                area=area_lookup["OPERACIONES"] or areas[0],
            ),
        ]
        requesters = [
            build_user(
                "req_camila",
                "Camila",
                "Ossandón",
                requester_group,
                is_critical=True,
                area=area_lookup["DIRECCIÓN EJECUTIVA"],
            ),
            build_user(
                "req_diego",
                "Diego",
                "Leiva",
                requester_group,
                area=area_lookup["FINANZAS"] or areas[3],
            ),
        ]

        return techs, requesters, admins

    # ------------------------------------------------------------------
    # Reglas y FAQs
    # ------------------------------------------------------------------
    def _create_autoassign_rules(self, categories, areas, techs):
        AutoAssignRule.objects.all().delete()
        cat_index = {c.name: c for c in categories}
        area_index = {a.name: a for a in areas}

        rules = [
            {"category": cat_index.get("INFRAESTRUCTURA"), "subcategory": None, "area": None, "tech": techs[0]},
            {
                "category": cat_index.get("SEGURIDAD"),
                "subcategory": Subcategory.objects.filter(name="MFA").first(),
                "area": None,
                "tech": techs[0],
            },
            {
                "category": cat_index.get("SOPORTE APLICACIONES"),
                "subcategory": Subcategory.objects.filter(name="ERP").first(),
                "area": area_index.get("OPERACIONES"),
                "tech": techs[1],
            },
            {"category": None, "subcategory": None, "area": area_index.get("DIRECCIÓN EJECUTIVA"), "tech": techs[1]},
            {"category": cat_index.get("DISPOSITIVOS"), "subcategory": None, "area": None, "tech": techs[1]},
        ]

        for r in rules:
            AutoAssignRule.objects.create(**r)

    def _create_faqs(self, categories, author):
        FAQ.objects.all().delete()
        payload = [
            (
                "Restablecer MFA",
                "Usa el portal de acceso seguro y valida tu identidad con el equipo de seguridad.",
                "SEGURIDAD",
                "MFA",
            ),
            (
                "Impresora sin conexión",
                "Revisa que esté en red corporativa y reinstala el driver desde el catálogo interno.",
                "DISPOSITIVOS",
                "IMPRESORA",
            ),
            (
                "Acceso ERP",
                "Solicita a tu jefe directo la aprobación en el portal y se asignará al equipo de aplicaciones.",
                "SOPORTE APLICACIONES",
                "ERP",
            ),
            (
                "Lentitud VPN",
                "Verifica tu ancho de banda y abre un ticket marcando prioridad ALTA si impacta operaciones críticas.",
                "INFRAESTRUCTURA",
                "VPN",
            ),
        ]
        cat_index = {c.name: c for c in categories}
        for question, answer, cat_name, sub_name in payload:
            FAQ.objects.create(
                question=question,
                answer=answer,
                category=cat_index.get(cat_name),
                subcategory=Subcategory.objects.filter(name=sub_name).first(),
                created_by=author,
                updated_by=author,
            )

    # ------------------------------------------------------------------
    # Tickets
    # ------------------------------------------------------------------
    def _build_status_plan(self, total: int):
        proportions = [
            (Ticket.OPEN, 0.32),
            (Ticket.IN_PROGRESS, 0.28),
            (Ticket.RESOLVED, 0.22),
            (Ticket.CLOSED, 0.18),
        ]
        plan: list[str] = []
        for status, pct in proportions:
            plan.extend([status] * int(total * pct))
        while len(plan) < total:
            plan.append(Ticket.OPEN)
        return plan[:total]

    def _create_tickets(self, *, status_plan, priorities, areas, categories, requesters):
        tickets = []
        now = timezone.now()
        span_days = 45
        base_created = now - timedelta(days=span_days)
        cadence_hours = max(1.0, (span_days * 24) / max(len(status_plan), 1))

        priority_cycle = priorities * ((len(status_plan) // len(priorities)) + 1)
        area_cycle = areas * ((len(status_plan) // len(areas)) + 1)

        for idx, status in enumerate(status_plan, start=1):
            requester = requesters[idx % len(requesters)]
            category = categories[idx % len(categories)]
            sub_qs = list(category.subcategories.all()) or list(Subcategory.objects.filter(category=category))
            subcategory = sub_qs[idx % len(sub_qs)] if sub_qs else None
            priority = priority_cycle[idx % len(priority_cycle)]
            area = area_cycle[idx % len(area_cycle)]

            created_at = base_created + timedelta(hours=idx * cadence_hours)
            if created_at > now:
                created_at = now - timedelta(hours=random.uniform(0.5, 6))
            title = f"Incidencia {idx:03d} en {category.name.title()}"
            description = (
                f"Ticket demo #{idx} para probar reportes y autoasignación. "
                f"Área {area.name.title()}, subcategoría {subcategory.name}."
            )

            ticket = Ticket.objects.create(
                code="",
                title=title,
                description=description,
                requester=requester,
                category=category,
                subcategory=subcategory,
                priority=priority,
                area=area,
                status=status,
                kind=Ticket.INCIDENT if idx % 3 == 0 else Ticket.REQUEST,
            )

            apply_auto_assign(ticket, actor=requester)

            resolved_at = None
            closed_at = None
            if status in (Ticket.RESOLVED, Ticket.CLOSED):
                resolved_at = created_at + timedelta(hours=12 + (idx % 48))
                if resolved_at > now:
                    resolved_at = now - timedelta(hours=random.uniform(0.5, 3))
            if status == Ticket.CLOSED:
                closed_at = (resolved_at or created_at) + timedelta(hours=4)
                if closed_at > now:
                    closed_at = now - timedelta(hours=random.uniform(0.25, 2))

            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
            )
            tickets.append(ticket)
        return tickets

    # ------------------------------------------------------------------
    # Purga
    # ------------------------------------------------------------------
    def _purge_demo_data(self):
        self.stdout.write(self.style.WARNING("Purga de datos previos (tickets, catálogos demo, FAQs, reglas)..."))
        Ticket.objects.all().delete()
        AutoAssignRule.objects.all().delete()
        FAQ.objects.all().delete()
        Subcategory.objects.all().delete()
        Category.objects.all().delete()
        Priority.objects.all().delete()
        Area.objects.all().delete()
        User.objects.filter(username__in=self._demo_usernames()).delete()

    def _demo_usernames(self):
        return ["admin_ana", "admin_bruno", "tech_ale", "tech_beto", "req_camila", "req_diego"]
