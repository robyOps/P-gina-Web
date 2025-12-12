"""
Crea un dataset de demostración rico en tickets, catálogos, usuarios y reglas.

- Ejecuta ``python manage.py load_demo_dataset --purge`` para borrar datos previos
  (tickets, catálogos demo y usuarios de prueba) y volver a generar todo.
- Genera por defecto 1000 tickets variados con categorías, subcategorías,
  prioridades, áreas, FAQs y reglas de autoasignación activas.
"""

from __future__ import annotations

import random
from collections import Counter
from itertools import cycle
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.roles import ROLE_ADMIN, ROLE_REQUESTER, ROLE_TECH
from catalog.models import Area, Category, Priority, Subcategory
from tickets.models import AutoAssignRule, FAQ, Ticket, TicketAssignment
from tickets.services import apply_auto_assign

User = get_user_model()


class Command(BaseCommand):
    help = "Carga un dataset de demostración con catálogos, usuarios y tickets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tickets",
            type=int,
            default=1000,
            help="Cantidad de tickets a generar (por defecto: 1000).",
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

        featured_specs = self._featured_ticket_templates(categories, areas, priorities, requesters)
        base_total = max(total_tickets - len(featured_specs), 0)
        status_plan = self._build_status_plan(base_total)
        tech_cycle = cycle(techs)

        tickets = self._create_tickets(
            status_plan=status_plan,
            priorities=priorities,
            areas=areas,
            categories=categories,
            requesters=requesters,
            tech_cycle=tech_cycle,
        )
        tickets.extend(
            self._create_featured_tickets(
                templates=featured_specs,
                areas=areas,
                categories=categories,
                priorities=priorities,
                requesters=requesters,
                tech_cycle=tech_cycle,
            )
        )
        counts = Counter([t.status for t in tickets])

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
                "Usuarios demo creados (password: Demo1234!) para roles de administración, técnicos y solicitantes."
            )
        )

    # ------------------------------------------------------------------
    # Catálogos
    # ------------------------------------------------------------------
    def _create_priorities(self):
        data = [
            ("BAJA", 144),
            ("MEDIA", 96),
            ("ALTA", 60),
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
            ("RIESGO Y CONTINUIDAD", True),
            ("RECURSOS HUMANOS", False),
        ]
        areas = []
        for name, is_critical in data:
            obj, _ = Area.objects.update_or_create(name=name, defaults={"is_critical": is_critical})
            areas.append(obj)
        return areas

    def _create_categories(self):
        data = [
            (
                "SOPORTE APLICACIONES",
                ["ERP", "CRM", "PAGOS", "API PARTNERS"],
                "Fallos funcionales y mejoras en sistemas de negocio.",
            ),
            (
                "INFRAESTRUCTURA",
                ["VPN", "WIFI", "CORREO", "ALMACENAMIENTO"],
                "Redes, accesos y servicios de conectividad.",
            ),
            (
                "SEGURIDAD",
                ["CREDENCIALES", "MFA", "ALERTAS SIEM", "RESPUESTA INCIDENTES"],
                "Gestión de identidades y alertas",
            ),
            (
                "DISPOSITIVOS",
                ["LAPTOP", "IMPRESORA", "PERIFÉRICOS", "MÓVILES"],
                "Hardware de usuario final",
            ),
            (
                "DATOS Y ANALÍTICA",
                ["ETL", "REPORTING", "DASHBOARDS"],
                "Pipelines, consultas y modelos de datos corporativos.",
            ),
            (
                "SOPORTE AL CLIENTE",
                ["TELEFONÍA", "CHAT", "HERRAMIENTAS DE CAMPO"],
                "Continuidad de las herramientas de experiencia cliente.",
            ),
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
            "RIESGO Y CONTINUIDAD": None,
            "RECURSOS HUMANOS": None,
            "INFRAESTRUCTURA": None,
            "SEGURIDAD": None,
            "DATOS Y ANALÍTICA": None,
            "SOPORTE AL CLIENTE": None,
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
            build_user("admin_carla", "Carla", "Mena", admin_group, is_staff=True, area=area_lookup["RIESGO Y CONTINUIDAD"]),
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
            build_user(
                "tech_cata",
                "Catalina",
                "Rivas",
                tech_group,
                area=area_lookup["EXPERIENCIA CLIENTE"],
            ),
            build_user(
                "tech_dante",
                "Dante",
                "Silva",
                tech_group,
                area=area_lookup.get("TECNOLOGÍA") or areas[1],
            ),
            build_user(
                "tech_eli",
                "Elisa",
                "Naranjo",
                tech_group,
                area=area_lookup["DATOS Y ANALÍTICA"] or areas[4],
            ),
            build_user(
                "tech_fede",
                "Federico",
                "Lagos",
                tech_group,
                area=area_lookup["RECURSOS HUMANOS"] or areas[6],
            ),
            build_user(
                "tech_gabi",
                "Gabriela",
                "Fuentes",
                tech_group,
                area=area_lookup["FINANZAS"] or areas[3],
            ),
            build_user(
                "tech_hugo",
                "Hugo",
                "Sanhueza",
                tech_group,
                area=area_lookup["INFRAESTRUCTURA"] or areas[1],
            ),
            build_user(
                "tech_isa",
                "Isabel",
                "Araya",
                tech_group,
                area=area_lookup["SEGURIDAD"] or areas[2],
            ),
            build_user(
                "tech_juan",
                "Juan",
                "Contreras",
                tech_group,
                area=area_lookup["SOPORTE AL CLIENTE"] or areas[5],
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
            build_user(
                "req_elena",
                "Elena",
                "Campos",
                requester_group,
                area=area_lookup["EXPERIENCIA CLIENTE"],
            ),
            build_user(
                "req_francisco",
                "Francisco",
                "Toro",
                requester_group,
                area=area_lookup["OPERACIONES"],
            ),
            build_user(
                "req_gracia",
                "Gracia",
                "Duarte",
                requester_group,
                is_critical=True,
                area=area_lookup["RIESGO Y CONTINUIDAD"],
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
            (
                "Recuperar credenciales olvidadas",
                "Ingresa a la página de autoservicio, responde tus preguntas de seguridad y restablece la contraseña.",
                "SEGURIDAD",
                "CREDENCIALES",
            ),
            (
                "Correo corporativo sin espacio",
                "Limpia la carpeta de enviados, vacía la papelera y solicita ampliación temporal de buzón si sigues al límite.",
                "INFRAESTRUCTURA",
                "ALMACENAMIENTO",
            ),
            (
                "Conexión Wi-Fi inestable",
                "Prioriza la red 5GHz, ubícate cerca del access point y reinicia el cliente para renovar tu lease DHCP.",
                "INFRAESTRUCTURA",
                "WIFI",
            ),
            (
                "Alta en el CRM",
                "Crea la solicitud indicando rol comercial y segmento; el equipo validará permisos antes de habilitar el acceso.",
                "SOPORTE APLICACIONES",
                "CRM",
            ),
            (
                "Error en conciliación de pagos",
                "Verifica que el archivo del procesador tenga el formato actualizado y vuelve a ejecutar el batch.",
                "SOPORTE APLICACIONES",
                "PAGOS",
            ),
            (
                "Integración con socio vía API",
                "Genera una nueva API key en el portal de partners y comparte el endpoint sandbox para pruebas.",
                "SOPORTE APLICACIONES",
                "API PARTNERS",
            ),
            (
                "Laptop requiere reemplazo",
                "Documenta el diagnóstico en el ticket y coordina retiro con mesa de servicio para recibir el equipo de backup.",
                "DISPOSITIVOS",
                "LAPTOP",
            ),
            (
                "Sin datos móviles en el teléfono corporativo",
                "Comprueba el perfil APN empresarial y reinicia el dispositivo; si persiste, solicita un eSIM de reemplazo.",
                "DISPOSITIVOS",
                "MÓVILES",
            ),
            (
                "Alerta de fraude reportada",
                "Escala de inmediato al equipo de respuesta a incidentes y aísla el endpoint sospechoso de la red.",
                "SEGURIDAD",
                "RESPUESTA INCIDENTES",
            ),
            (
                "Dashboard no carga datos",
                "Verifica que el dataset esté actualizado y limpia la caché del navegador antes de recargar el panel.",
                "DATOS Y ANALÍTICA",
                "DASHBOARDS",
            ),
            (
                "Ejecución ETL fallida",
                "Revisa los logs en el orquestador, valida credenciales del data lake y relanza el job manualmente.",
                "DATOS Y ANALÍTICA",
                "ETL",
            ),
            (
                "Chat con clientes fuera de línea",
                "Confirma que los agentes estén logueados en la herramienta y revisa el estado del conector de mensajería.",
                "SOPORTE AL CLIENTE",
                "CHAT",
            ),
            (
                "Llamadas sin audio en telefonía",
                "Verifica el enrutamiento en el SBC y realiza una prueba loopback para descartar fallas de headset.",
                "SOPORTE AL CLIENTE",
                "TELEFONÍA",
            ),
            (
                "App de campo no sincroniza",
                "Pide a los técnicos actualizar la app, habilitar datos en segundo plano y sincronizar cuando tengan señal estable.",
                "SOPORTE AL CLIENTE",
                "HERRAMIENTAS DE CAMPO",
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
            (Ticket.OPEN, 0.27),
            (Ticket.IN_PROGRESS, 0.27),
            (Ticket.RESOLVED, 0.24),
            (Ticket.CLOSED, 0.22),
        ]
        plan: list[str] = []
        for status, pct in proportions:
            plan.extend([status] * int(total * pct))
        while len(plan) < total:
            plan.append(Ticket.IN_PROGRESS if len(plan) % 2 else Ticket.OPEN)
        return plan[:total]

    def _create_tickets(self, *, status_plan, priorities, areas, categories, requesters, tech_cycle):
        tickets = []
        now = timezone.now()
        start_of_year = now.replace(month=1, day=1, hour=9, minute=0, second=0, microsecond=0)
        total_hours = max((now - start_of_year).total_seconds() / 3600.0, 1.0)
        cadence_hours = total_hours / max(len(status_plan), 1)

        priority_cycle = priorities * ((len(status_plan) // len(priorities)) + 1)
        area_cycle = areas * ((len(status_plan) // len(areas)) + 1)

        for idx, status in enumerate(status_plan, start=1):
            requester = requesters[idx % len(requesters)]
            category = categories[idx % len(categories)]
            sub_qs = list(category.subcategories.all()) or list(Subcategory.objects.filter(category=category))
            subcategory = sub_qs[idx % len(sub_qs)] if sub_qs else None
            priority = priority_cycle[idx % len(priority_cycle)]
            area = area_cycle[idx % len(area_cycle)]

            created_at = start_of_year + timedelta(hours=idx * cadence_hours)
            created_at += timedelta(hours=random.uniform(-6, 12))
            if status in (Ticket.OPEN, Ticket.IN_PROGRESS) and created_at < now - timedelta(days=90):
                created_at = now - timedelta(days=random.uniform(2, 90))
            if priority.name == "CRÍTICA" and created_at < now - timedelta(days=10):
                created_at = now - timedelta(hours=random.uniform(priority.sla_hours * 0.5, priority.sla_hours * 4))
            if created_at > now:
                created_at = now - timedelta(hours=random.uniform(0.5, 6))
            title = f"Ticket demo {idx:03d} en {category.name.title()}"
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

            chosen_tech = next(tech_cycle)
            self._assign_ticket(ticket, to_user=chosen_tech, created_at=created_at, actor=requester)

            ticket.assignments.update(created_at=created_at)

            resolved_at = None
            closed_at = None
            if status in (Ticket.RESOLVED, Ticket.CLOSED):
                sla_factor = random.uniform(0.6, 1.45)
                resolved_at = created_at + timedelta(hours=priority.sla_hours * sla_factor)
                if resolved_at > now:
                    resolved_at = now - timedelta(hours=random.uniform(1, 8))
            if status == Ticket.CLOSED:
                closed_at = (resolved_at or created_at) + timedelta(hours=random.uniform(2, 10))
                if closed_at > now:
                    closed_at = now - timedelta(hours=random.uniform(0.5, 4))

            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
            )
            tickets.append(ticket)
        return tickets

    def _featured_ticket_templates(self, categories, areas, priorities, requesters):
        cat_index = {c.name: c for c in categories}
        area_index = {a.name: a for a in areas}
        priority_index = {p.name: p for p in priorities}
        critical_requester = next(
            (u for u in requesters if getattr(getattr(u, "profile", None), "is_critical_actor", False)), requesters[0]
        )
        return [
            {
                "title": "Alerta crítica en VPN corporativa",
                "category": cat_index.get("INFRAESTRUCTURA"),
                "subcategory": Subcategory.objects.filter(name="VPN").first(),
                "priority": priority_index.get("CRÍTICA"),
                "area": area_index.get("RIESGO Y CONTINUIDAD") or area_index.get("TECNOLOGÍA"),
                "status": Ticket.IN_PROGRESS,
                "requester": critical_requester,
                "created_offset_hours": 10,
            },
            {
                "title": "Escalamiento ejecutivo por canal digital",
                "category": cat_index.get("SOPORTE AL CLIENTE"),
                "subcategory": Subcategory.objects.filter(name="CHAT").first(),
                "priority": priority_index.get("ALTA"),
                "area": area_index.get("EXPERIENCIA CLIENTE"),
                "status": Ticket.OPEN,
                "requester": critical_requester,
                "created_offset_hours": 4,
            },
            {
                "title": "Caso en modelo de datos financiero",
                "category": cat_index.get("DATOS Y ANALÍTICA"),
                "subcategory": Subcategory.objects.filter(name="REPORTING").first(),
                "priority": priority_index.get("MEDIA"),
                "area": area_index.get("FINANZAS"),
                "status": Ticket.OPEN,
                "requester": random.choice(requesters),
                "created_offset_hours": 72,
            },
        ]

    def _create_featured_tickets(self, *, templates, areas, categories, priorities, requesters, tech_cycle):
        now = timezone.now()
        tickets = []
        for spec in templates:
            created_at = now - timedelta(hours=spec.get("created_offset_hours", 6))
            ticket = Ticket.objects.create(
                code="",
                title=spec["title"],
                description="Ticket destacado para validar reglas de SLA y criticidad.",
                requester=spec["requester"],
                category=spec.get("category") or random.choice(categories),
                subcategory=spec.get("subcategory"),
                priority=spec.get("priority") or random.choice(priorities),
                area=spec.get("area") or random.choice(areas),
                status=spec.get("status", Ticket.OPEN),
                kind=Ticket.INCIDENT,
            )
            apply_auto_assign(ticket, actor=spec["requester"])
            self._assign_ticket(
                ticket,
                to_user=next(tech_cycle),
                created_at=created_at,
                actor=spec["requester"],
                reason="distribución destacada",
            )
            ticket.assignments.update(created_at=created_at)
            Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at)
            tickets.append(ticket)
        return tickets

    def _assign_ticket(self, ticket, *, to_user, created_at, actor=None, reason="distribución demo"):
        previous = ticket.assigned_to
        if ticket.assigned_to_id != to_user.id:
            ticket.assigned_to = to_user
            ticket.save(update_fields=["assigned_to", "updated_at"])

        assignment = TicketAssignment.objects.create(
            ticket=ticket,
            from_user=actor or previous,
            to_user=to_user,
            reason=reason,
        )
        TicketAssignment.objects.filter(pk=assignment.pk).update(created_at=created_at)

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
        return [
            "admin_ana",
            "admin_bruno",
            "admin_carla",
            "tech_ale",
            "tech_beto",
            "tech_cata",
            "tech_dante",
            "tech_eli",
            "tech_fede",
            "tech_gabi",
            "tech_hugo",
            "tech_isa",
            "tech_juan",
            "req_camila",
            "req_diego",
            "req_elena",
            "req_francisco",
            "req_gracia",
        ]
