"""
Crea un dataset de demostración rico en tickets, catálogos, usuarios y reglas.

- Ejecuta ``python manage.py load_demo_dataset --purge`` para borrar datos previos
  (tickets, catálogos demo y usuarios de prueba) y volver a generar todo.
- Por defecto genera un escenario 2025 con 2.200 tickets realistas, 300
  solicitantes, 6 técnicos y 2 administradores, incluyendo reglas de autoasignación
  y actividad reciente en diciembre.
"""

from __future__ import annotations

import random
from collections import Counter
from itertools import cycle
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.roles import ROLE_ADMIN, ROLE_REQUESTER, ROLE_TECH
from catalog.models import Area, Category, Priority, Subcategory
from tickets.models import AutoAssignRule, AuditLog, FAQ, Ticket, TicketAssignment, TicketComment
from tickets.services import apply_auto_assign

User = get_user_model()


class Command(BaseCommand):
    help = "Carga un dataset de demostración con catálogos, usuarios y tickets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tickets",
            type=int,
            default=2200,
            help="Cantidad de tickets a generar (por defecto: 2200).",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Elimina tickets, catálogos demo, FAQs y usuarios de prueba antes de crear el dataset.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Alias de --purge para limpiar datos previos antes de crear el dataset.",
        )
        parser.add_argument(
            "--requesters",
            type=int,
            default=300,
            help="Cantidad de usuarios solicitantes a generar (por defecto: 300).",
        )
        parser.add_argument(
            "--techs",
            type=int,
            default=6,
            help="Cantidad de técnicos resolutores (por defecto: 6).",
        )
        parser.add_argument(
            "--admins",
            type=int,
            default=2,
            help="Cantidad de administradores (por defecto: 2).",
        )
        parser.add_argument(
            "--start",
            type=str,
            default="2025-01-01",
            help="Fecha inicial del dataset (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--end",
            type=str,
            default="2025-12-12",
            help="Fecha final del dataset (YYYY-MM-DD).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        start_date = datetime.fromisoformat(options["start"]).date()
        end_date = datetime.fromisoformat(options["end"]).date()
        total_tickets = max(200, min(options["tickets"], 9110))
        purge = options["purge"] or options["reset"]
        total_requesters = max(50, min(options["requesters"], 800))
        total_techs = max(2, min(options["techs"], 20))
        total_admins = max(1, min(options["admins"], 6))

        # Distribución de asignación: mayoría autoasignada, pero con espacio para
        # manual/self-assign y tickets sin asignar (especialmente recientes).
        self.auto_assign_rate = 0.55
        self.manual_assign_rate = 0.55
        self.self_assign_rate = 0.25
        self.reassign_rate = random.uniform(0.1, 0.2)

        # Control de SLA en tiempo real.
        self.sla_counters = {
            "closed_total": 0,
            "closed_breach": 0,
            "open_total": 0,
            "open_breach": 0,
        }
        self.start_date = start_date
        self.end_date = end_date
        random.seed(202501)

        self.stdout.write(self.style.WARNING("Inicializando grupos y permisos base (init_rbac)..."))
        call_command("init_rbac")

        if purge:
            self._purge_demo_data()

        priorities = self._create_priorities()
        areas = self._create_areas()
        categories = self._create_categories()
        techs, requesters, admins = self._create_users(
            areas,
            total_requesters=total_requesters,
            total_techs=total_techs,
            total_admins=total_admins,
        )

        self.requester_weights = self._build_requester_weights(requesters)

        self._create_autoassign_rules(categories, areas, techs)
        self._create_faqs(categories, requesters[0])

        featured_specs = self._featured_ticket_templates(categories, areas, priorities, requesters)
        base_total = max(total_tickets - len(featured_specs), 0)
        tech_cycle = cycle(techs)

        tickets = self._create_tickets(
            total=base_total,
            priorities=priorities,
            areas=areas,
            categories=categories,
            requesters=requesters,
            tech_cycle=tech_cycle,
            admins=admins,
        )
        tickets.extend(
            self._create_featured_tickets(
                templates=featured_specs,
                areas=areas,
                categories=categories,
                priorities=priorities,
                requesters=requesters,
                tech_cycle=tech_cycle,
                admins=admins,
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
        closed_total = max(self.sla_counters["closed_total"], 1)
        open_total = max(counts[Ticket.OPEN] + counts[Ticket.IN_PROGRESS], 1)
        closed_breach_pct = (self.sla_counters["closed_breach"] / closed_total) * 100
        open_breach_pct = (self.sla_counters["open_breach"] / open_total) * 100
        unassigned_count = Ticket.objects.filter(assigned_to__isnull=True).count()

        total = len(tickets)
        pct = lambda val: (val / total) * 100 if total else 0
        self.stdout.write(
            self.style.WARNING(
                "Distribución por estado: "
                f"OPEN {counts[Ticket.OPEN]} ({pct(counts[Ticket.OPEN]):.1f}%) | "
                f"IN_PROGRESS {counts[Ticket.IN_PROGRESS]} ({pct(counts[Ticket.IN_PROGRESS]):.1f}%) | "
                f"RESOLVED {counts[Ticket.RESOLVED]} ({pct(counts[Ticket.RESOLVED]):.1f}%) | "
                f"CLOSED {counts[Ticket.CLOSED]} ({pct(counts[Ticket.CLOSED]):.1f}%)"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Resumen SLA: "
                f"Cerrados dentro SLA {(100 - closed_breach_pct):.1f}% | "
                f"Fuera SLA {closed_breach_pct:.1f}% | "
                f"Vencidos abiertos {open_breach_pct:.1f}%"
            )
        )
        self.stdout.write(self.style.WARNING(f"Tickets sin asignar: {unassigned_count}"))
        self.stdout.write(
            self.style.WARNING(
                "Usuarios demo creados (password: Demo1234!) para roles de administración, técnicos y solicitantes."
            )
        )

        tz = timezone.get_current_timezone()
        end_cap = timezone.make_aware(
            datetime(self.end_date.year, self.end_date.month, self.end_date.day, 23, 59, 59), tz
        )
        stale_open = Ticket.objects.filter(
            status__in=[Ticket.OPEN, Ticket.IN_PROGRESS], created_at__lt=end_cap - timedelta(days=21)
        ).count()
        critical_old = Ticket.objects.filter(
            status__in=[Ticket.OPEN, Ticket.IN_PROGRESS],
            priority__name="CRÍTICA",
            created_at__lt=end_cap - timedelta(days=3),
        ).count()
        high_old = Ticket.objects.filter(
            status__in=[Ticket.OPEN, Ticket.IN_PROGRESS],
            priority__name="ALTA",
            created_at__lt=end_cap - timedelta(days=7),
        ).count()

        urgent_overdue = Ticket.objects.filter(
            status__in=[Ticket.OPEN, Ticket.IN_PROGRESS], priority__name__in=["CRÍTICA", "ALTA"]
        )
        max_overdue = 0
        for t in urgent_overdue:
            due_at = t.created_at + timedelta(hours=t.priority.sla_hours)
            if due_at < end_cap:
                overdue_hours = (end_cap - due_at).total_seconds() / 3600
                max_overdue = max(max_overdue, overdue_hours)

        self.stdout.write(
            self.style.NOTICE(
                f"OPEN/IN_PROGRESS >21 días: {stale_open} | "
                f"CRÍTICA >3d activos: {critical_old} | ALTA >7d activos: {high_old} | "
                f"Máx overdue urgentes (h): {max_overdue:.1f}"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                f"Closed fuera de SLA: {closed_breach_pct:.1f}% | Vencidos abiertos: {open_breach_pct:.1f}%"
            )
        )

    # ------------------------------------------------------------------
    # Catálogos
    # ------------------------------------------------------------------
    def _create_priorities(self):
        data = [
            ("BAJA", 72),
            ("MEDIA", 24),
            ("ALTA", 8),
            ("CRÍTICA", 4),
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
    def _requester_seed_data(self):
        base_requesters = [
            ("req_camila", "Camila", "Ossandon", "DIRECCIÓN EJECUTIVA", True),
            ("req_diego", "Diego", "Leiva", "FINANZAS", False),
            ("req_elena", "Elena", "Campos", "EXPERIENCIA CLIENTE", False),
            ("req_francisco", "Francisco", "Toro", "OPERACIONES", False),
            ("req_gracia", "Gracia", "Duarte", "RIESGO Y CONTINUIDAD", True),
        ]
        extra_first_names = [
            "Irene",
            "Javier",
            "Karla",
            "Luis",
            "Maria",
            "Nicolas",
            "Olga",
            "Pablo",
            "Rodrigo",
            "Sofia",
            "Tamara",
            "Ulises",
            "Valeria",
            "Walter",
            "Ximena",
            "Yolanda",
            "Zoe",
            "Andres",
            "Beatriz",
            "Carmen",
            "Daniel",
            "Esteban",
            "Fernanda",
            "German",
            "Hilda",
            "Ivan",
            "Julia",
            "Kevin",
            "Lucia",
            "Manuel",
            "Natalia",
            "Oscar",
            "Patricia",
            "Rafael",
            "Sara",
            "Tomas",
            "Victoria",
            "Wendy",
            "Xavier",
            "Yael",
            "Antonella",
            "Bruno",
            "Claudia",
            "Dante",
            "Elsa",
            "Felipe",
            "Gonzalo",
            "Helena",
            "Ismael",
            "Jonas",
            "Karen",
            "Leonor",
            "Matias",
            "Noelia",
            "Orlando",
            "Paula",
            "Quentin",
            "Rocio",
        ]
        extra_last_names = [
            "Aguilar",
            "Baeza",
            "Contreras",
            "Dominguez",
            "Escobar",
            "Fuentes",
            "Gonzalez",
            "Hernandez",
            "Ibarra",
            "Jimenez",
            "Keller",
            "Lagos",
            "Maldonado",
            "Navarro",
            "Ortega",
            "Paredes",
            "Quinteros",
            "Ramos",
            "Salinas",
            "Tapia",
            "Ulloa",
            "Vargas",
            "Weiss",
            "Xiques",
            "Yanez",
            "Zuñiga",
            "Arriagada",
            "Bravo",
            "Carrasco",
            "Donoso",
            "Espinoza",
            "Figueroa",
            "Garrido",
            "Huerta",
            "Inostroza",
            "Jara",
            "Kurtz",
            "Leal",
            "Muñoz",
            "Nieto",
            "Ochoa",
            "Palma",
            "Quezada",
            "Riquelme",
            "Saavedra",
            "Toledo",
            "Uribe",
            "Valdes",
            "Warner",
            "Xelhuantzi",
            "Yepez",
            "Zuleta",
        ]
        return base_requesters, extra_first_names, extra_last_names

    def _create_users(self, areas, *, total_requesters: int, total_techs: int, total_admins: int):
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

        admin_specs = [
            ("admin_ana", "Ana", "Pérez", "DIRECCIÓN EJECUTIVA"),
            ("admin_bruno", "Bruno", "Salas", "TECNOLOGÍA"),
            ("admin_carla", "Carla", "Mena", "RIESGO Y CONTINUIDAD"),
        ]
        if total_admins > len(admin_specs):
            extra_admins = []
            for idx in range(total_admins - len(admin_specs)):
                first = extra_first_names[idx % len(extra_first_names)]
                last = extra_last_names[(idx * 2) % len(extra_last_names)]
                area_key = list(area_lookup.keys())[(idx + 3) % len(area_lookup)]
                extra_admins.append((f"admin_ext_{idx+1:02d}", first, last, area_key))
            admin_specs.extend(extra_admins)
        admins = [
            build_user(username, first, last, admin_group, is_staff=True, area=area_lookup.get(area_key))
            for username, first, last, area_key in admin_specs[:total_admins]
        ]

        tech_specs = [
            ("tech_ale", "Ale", "Valdés", "TECNOLOGÍA"),
            ("tech_beto", "Beto", "Ramos", "OPERACIONES"),
            ("tech_cata", "Catalina", "Rivas", "EXPERIENCIA CLIENTE"),
            ("tech_dante", "Dante", "Silva", "TECNOLOGÍA"),
            ("tech_eli", "Elisa", "Naranjo", "DATOS Y ANALÍTICA"),
            ("tech_fede", "Federico", "Lagos", "RECURSOS HUMANOS"),
            ("tech_gabi", "Gabriela", "Fuentes", "FINANZAS"),
            ("tech_hugo", "Hugo", "Sanhueza", "INFRAESTRUCTURA"),
            ("tech_isa", "Isabel", "Araya", "SEGURIDAD"),
            ("tech_juan", "Juan", "Contreras", "SOPORTE AL CLIENTE"),
        ]
        if total_techs > len(tech_specs):
            for idx in range(total_techs - len(tech_specs)):
                first = extra_first_names[(idx + 5) % len(extra_first_names)]
                last = extra_last_names[(idx * 4) % len(extra_last_names)]
                area_key = list(area_lookup.keys())[(idx + 5) % len(area_lookup)]
                tech_specs.append((f"tech_ext_{idx+1:02d}", first, last, area_key))
        techs = [
            build_user(
                username,
                first,
                last,
                tech_group,
                area=area_lookup.get(area_key) or random.choice(areas),
            )
            for username, first, last, area_key in tech_specs[:total_techs]
        ]

        base_requesters, extra_first_names, extra_last_names = self._requester_seed_data()
        critical_sample = set(random.sample(range(total_requesters), k=max(8, int(total_requesters * 0.05))))
        area_keys = list(area_lookup.keys())

        generated_requesters = []
        for idx in range(max(total_requesters - len(base_requesters), 0)):
            first = extra_first_names[idx % len(extra_first_names)]
            last = extra_last_names[(idx * 3) % len(extra_last_names)]
            username = f"req_{first.lower()}_{idx + 1:03d}"
            area_key = area_keys[idx % len(area_keys)]
            generated_requesters.append(
                (
                    username,
                    first,
                    last,
                    area_key,
                    idx in critical_sample,
                )
            )

        requester_specs = (base_requesters + generated_requesters)[:total_requesters]
        requesters = []
        for username, first, last, area_key, is_critical in requester_specs:
            requesters.append(
                build_user(
                    username,
                    first,
                    last,
                    requester_group,
                    is_critical=is_critical,
                    area=area_lookup.get(area_key) or random.choice(areas),
                )
            )

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
    def _create_tickets(self, *, total, priorities, areas, categories, requesters, tech_cycle, admins):
        tickets = []
        tz = timezone.get_current_timezone()
        end_cap = timezone.make_aware(
            datetime(self.end_date.year, self.end_date.month, self.end_date.day, 23, 59, 59), tz
        )
        created_schedule = self._build_created_at_schedule(total, tz, self.start_date, self.end_date)
        start_cap = timezone.make_aware(
            datetime(self.start_date.year, self.start_date.month, self.start_date.day, 0, 0, 0), tz
        )

        priority_cycle = priorities * ((len(created_schedule) // len(priorities)) + 1)
        area_cycle = areas * ((len(created_schedule) // len(areas)) + 1)

        for idx, created_at in enumerate(created_schedule, start=1):
            status = self._choose_status_by_age(created_at=created_at, end_cap=end_cap)
            requester = random.choices(requesters, weights=self.requester_weights, k=1)[0]
            category = categories[idx % len(categories)]
            sub_qs = list(category.subcategories.all()) or list(Subcategory.objects.filter(category=category))
            subcategory = sub_qs[idx % len(sub_qs)] if sub_qs else None
            priority = priority_cycle[idx % len(priority_cycle)]
            area = area_cycle[idx % len(area_cycle)]

            if status in (Ticket.OPEN, Ticket.IN_PROGRESS):
                created_at = self._maybe_mark_open_overdue(
                    created_at=created_at, priority=priority, end_cap=end_cap, start_cap=start_cap
                )

            status = self._enforce_status_recency(
                status=status, created_at=created_at, end_cap=end_cap, priority=priority
            )
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

            auto_prob = self._auto_assign_probability(created_at, end_cap)
            auto_flag = random.random() < auto_prob
            auto_assigned, assignment_time = self._normalize_auto_assignment(ticket, created_at, force=auto_flag)

            chosen_tech = next(tech_cycle)
            if not auto_assigned:
                strategy = self._pick_assignment_strategy(created_at=created_at, end_cap=end_cap)
                assignment_time = created_at + timedelta(minutes=random.randint(5, 45))
                if strategy == "MANUAL_ASSIGN":
                    actor = random.choice(admins)
                    self._assign_ticket(
                        ticket,
                        to_user=chosen_tech,
                        created_at=assignment_time,
                        actor=actor,
                        reason="MANUAL_ASSIGN",
                    )
                elif strategy == "TECH_SELF_ASSIGN":
                    self._assign_ticket(
                        ticket,
                        to_user=chosen_tech,
                        created_at=assignment_time,
                        actor=chosen_tech,
                        reason="TECH_SELF_ASSIGN",
                    )
                else:
                    assignment_time = None

            resolved_at, closed_at = self._build_resolution_timestamps(
                status=status,
                created_at=created_at,
                priority=priority,
                end_cap=end_cap,
            )

            last_assignment_at = assignment_time or created_at
            last_assignment_at = self._maybe_reassign(
                ticket=ticket,
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                tech_cycle=tech_cycle,
                admins=admins,
            )

            audit_latest = self._create_audit_trail(
                ticket=ticket,
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                actor=requester,
            )

            updated_at_candidates = [created_at, resolved_at, closed_at, last_assignment_at, audit_latest]
            updated_at = max([dt for dt in updated_at_candidates if dt]) if any(updated_at_candidates) else created_at

            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                updated_at=updated_at,
            )
            tickets.append(ticket)
        return tickets

    def _build_created_at_schedule(self, total: int, tz, start_date, end_date):
        """Genera fechas realistas entre ``start_date`` y ``end_date``.

        Aplica una carga de ~8-10 tickets por día hábil y menor volumen en
        fines de semana, conservando actividad reciente en diciembre.
        """

        start = timezone.make_aware(datetime(start_date.year, start_date.month, start_date.day, 0, 0), tz)
        end = timezone.make_aware(datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59), tz)

        days = []
        current = start
        while current.date() <= end.date():
            is_weekday = current.weekday() < 5
            base = random.randint(8, 10) if is_weekday else random.randint(1, 3)
            days.append((current, base))
            current += timedelta(days=1)

        total_raw = sum(count for _, count in days)
        scale = total / total_raw if total_raw else 1
        day_buckets = []
        for day, base in days:
            scaled = max(1, int(round(base * scale))) if day.weekday() >= 5 else max(7, int(round(base * scale)))
            day_buckets.append([day, scaled])

        # Ajusta diferencias para alcanzar el total exacto
        current_total = sum(count for _, count in day_buckets)
        while current_total < total:
            target_days = [idx for idx, (day, _) in enumerate(day_buckets) if day.weekday() < 5]
            idx = random.choice(target_days)
            day_buckets[idx][1] += 1
            current_total += 1
        while current_total > total:
            candidates = [idx for idx, (day, count) in enumerate(day_buckets) if count > 1]
            idx = random.choice(candidates)
            day_buckets[idx][1] -= 1
            current_total -= 1

        schedule = []
        december_forced = []
        december_candidates = [
            datetime(end_date.year, 12, 5, 10, 30),
            datetime(end_date.year, 12, 9, 15, 10),
            datetime(end_date.year, 12, 11, 11, 45),
        ]
        for candidate in december_candidates:
            if start_date <= candidate.date() <= end_date:
                december_forced.append(timezone.make_aware(candidate, tz))

        for day, count in day_buckets:
            for _ in range(count):
                if random.random() < 0.9:
                    hour = random.randint(8, 19)
                else:
                    hour = random.randint(0, 23)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                created_at = timezone.make_aware(
                    datetime(day.year, day.month, day.day, hour, minute, second), tz
                )
                created_at = min(created_at, end)
                schedule.append(created_at)

        schedule.extend(december_forced)
        schedule = sorted(schedule)
        forced_set = set(december_forced)
        while len(schedule) > total:
            removable = [idx for idx, dt in enumerate(schedule) if dt not in forced_set and schedule[idx].weekday() >= 5]
            if not removable:
                removable = [idx for idx, dt in enumerate(schedule) if dt not in forced_set]
            if not removable:
                schedule.pop()
                continue
            schedule.pop(removable[0])
        return schedule[:total]

    def _enforce_status_recency(self, *, status, created_at, end_cap, priority):
        """Evita tickets activos muy antiguos y urgentes envejecidos."""

        if status not in (Ticket.OPEN, Ticket.IN_PROGRESS):
            return status

        age_days = (end_cap.date() - created_at.date()).days
        forced_weights = (Ticket.RESOLVED, Ticket.CLOSED)
        forced_prob = (0.35, 0.65)

        if age_days > 21:
            return random.choices(forced_weights, weights=forced_prob, k=1)[0]

        priority_name = (priority.name or "").upper()
        if priority_name == "CRÍTICA" and age_days > 3:
            return random.choices(forced_weights, weights=(0.45, 0.55), k=1)[0]
        if priority_name == "ALTA" and age_days > 7:
            return random.choices(forced_weights, weights=(0.4, 0.6), k=1)[0]

        return status

    def _choose_status_by_age(self, *, created_at, end_cap):
        days_old = (end_cap.date() - created_at.date()).days

        if days_old <= 3:
            choices = [
                (Ticket.OPEN, 0.35),
                (Ticket.IN_PROGRESS, 0.4),
                (Ticket.RESOLVED, 0.15),
                (Ticket.CLOSED, 0.1),
            ]
        elif days_old <= 7:
            choices = [
                (Ticket.OPEN, 0.28),
                (Ticket.IN_PROGRESS, 0.32),
                (Ticket.RESOLVED, 0.22),
                (Ticket.CLOSED, 0.18),
            ]
        elif days_old <= 14:
            choices = [
                (Ticket.OPEN, 0.1),
                (Ticket.IN_PROGRESS, 0.25),
                (Ticket.RESOLVED, 0.35),
                (Ticket.CLOSED, 0.3),
            ]
        elif days_old <= 30:
            choices = [
                (Ticket.OPEN, 0.05),
                (Ticket.IN_PROGRESS, 0.12),
                (Ticket.RESOLVED, 0.33),
                (Ticket.CLOSED, 0.5),
            ]
        elif days_old <= 60:
            choices = [
                (Ticket.OPEN, 0.01),
                (Ticket.IN_PROGRESS, 0.03),
                (Ticket.RESOLVED, 0.35),
                (Ticket.CLOSED, 0.61),
            ]
        else:
            choices = [
                (Ticket.OPEN, 0.001),
                (Ticket.IN_PROGRESS, 0.007),
                (Ticket.RESOLVED, 0.32),
                (Ticket.CLOSED, 0.672),
            ]

        roll = random.random()
        cumulative = 0
        for status, weight in choices:
            cumulative += weight
            if roll <= cumulative:
                return status
        return choices[-1][0]

    def _pick_assignment_strategy(self, *, created_at, end_cap):
        days_from_end = (end_cap.date() - created_at.date()).days
        unassigned_target = random.uniform(0.25, 0.4) if days_from_end <= 10 else random.uniform(0.1, 0.2)

        manual = self.manual_assign_rate
        self_assign = self.self_assign_rate
        total = manual + self_assign + unassigned_target
        roll = random.random() * total
        if roll < manual:
            return "MANUAL_ASSIGN"
        if roll < manual + self_assign:
            return "TECH_SELF_ASSIGN"
        return "UNASSIGNED"

    def _auto_assign_probability(self, created_at, end_cap):
        days_from_end = (end_cap.date() - created_at.date()).days
        if days_from_end <= 10:
            return 0.4
        return self.auto_assign_rate

    def _normalize_auto_assignment(self, ticket, created_at, *, force=True):
        if not force:
            return False, None

        auto_assigned = apply_auto_assign(ticket, actor=None)
        assignment = ticket.assignments.order_by("-created_at", "-pk").first()
        if ticket.assigned_to_id and assignment:
            auto_time = created_at + timedelta(minutes=random.randint(3, 30))
            TicketAssignment.objects.filter(pk=assignment.pk).update(
                created_at=auto_time, from_user=None, reason="AUTO_ASSIGN_RULE"
            )
            audit = AuditLog.objects.filter(ticket=ticket, action="ASSIGN").order_by("-created_at", "-pk").first()
            if audit:
                meta = audit.meta or {}
                meta.update({"reason": "AUTO_ASSIGN_RULE"})
                audit.meta = meta
                audit.created_at = auto_time
                audit.save(update_fields=["meta", "created_at"])
            return True, auto_time
        return auto_assigned, None

    def _should_breach_closed(self):
        total = max(self.sla_counters["closed_total"], 1)
        breach = self.sla_counters["closed_breach"] / total
        if breach < 0.08:
            return random.random() < 0.15
        if breach < 0.1:
            return random.random() < 0.12
        if breach < 0.12:
            return random.random() < 0.08
        return random.random() < 0.03

    def _build_resolution_timestamps(self, *, status, created_at, priority, end_cap):
        """Crea timestamps de resolución/cierre controlando proporción de SLA."""

        if status not in (Ticket.RESOLVED, Ticket.CLOSED):
            return None, None

        self.sla_counters["closed_total"] += 1
        due_at = created_at + timedelta(hours=priority.sla_hours)
        out_of_sla = self._should_breach_closed()

        if out_of_sla:
            self.sla_counters["closed_breach"] += 1
            factor = random.uniform(1.05, 1.8)
        else:
            factor = random.uniform(0.5, 0.95)

        resolved_at = created_at + timedelta(hours=priority.sla_hours * factor)
        if not out_of_sla and resolved_at > due_at:
            resolved_at = due_at - timedelta(hours=random.uniform(0.1, max(priority.sla_hours * 0.2, 0.5)))
        if resolved_at < created_at:
            resolved_at = created_at + timedelta(hours=random.uniform(0.2, 2))
        if resolved_at > end_cap:
            resolved_at = end_cap - timedelta(hours=random.uniform(0.2, 6))

        closed_at = None
        if status == Ticket.CLOSED:
            closed_at = resolved_at + timedelta(hours=random.uniform(1.5, 12))
            if closed_at > end_cap:
                closed_at = end_cap

        return resolved_at, closed_at

    def _maybe_reassign(self, *, ticket, created_at, resolved_at, closed_at, tech_cycle, admins):
        """Agrega re-asignaciones distribuidas en el tiempo."""

        last_assignment = ticket.assignments.order_by("-created_at").first()
        last_at = last_assignment.created_at if last_assignment else created_at

        span_end = closed_at or resolved_at
        if not span_end:
            span_end = created_at + timedelta(hours=random.uniform(1, 12))

        if random.random() < self.reassign_rate:
            reassign_time = created_at + timedelta(hours=random.uniform(0.5, max((span_end - created_at).total_seconds() / 3600, 1)))
            reassign_time = min(reassign_time, span_end)
            self._assign_ticket(
                ticket,
                to_user=next(tech_cycle),
                created_at=reassign_time,
                actor=random.choice(admins),
                reason="REASSIGN",
            )
            last_at = reassign_time

        return last_at

    def _maybe_mark_open_overdue(self, *, created_at, priority, end_cap, start_cap):
        """Marca pocos tickets abiertos/en progreso como vencidos de forma controlada."""

        target_active = 53
        target_breach = 6

        self.sla_counters["open_total"] += 1
        ratio = self.sla_counters["open_breach"] / max(self.sla_counters["open_total"], 1)

        mark = False
        if self.sla_counters["open_total"] <= target_active:
            remaining_slots = target_active - self.sla_counters["open_total"]
            remaining_breaches = max(target_breach - self.sla_counters["open_breach"], 0)

            if remaining_breaches and remaining_slots < remaining_breaches:
                mark = True
            elif remaining_breaches:
                probability = max(0.15, min(0.55, remaining_breaches / max(remaining_slots + 1, 1)))
                mark = random.random() < probability
        else:
            target_ratio = target_breach / target_active
            if ratio < 0.04:
                probability = 0.18
            elif ratio < 0.06:
                probability = 0.12
            elif ratio < target_ratio:
                probability = 0.08
            elif ratio < 0.1:
                probability = 0.04
            elif ratio < 0.12:
                probability = 0.02
            else:
                probability = 0.01

            mark = random.random() < probability

        if not mark:
            return created_at

        max_overdue_hours = {
            "CRÍTICA": 6,
            "ALTA": 24,
            "MEDIA": 48,
            "BAJA": 72,
        }.get((priority.name or "").upper(), 48)

        overdue_hours = random.uniform(0.5, min(max_overdue_hours, priority.sla_hours * 0.35))
        target_due = end_cap - timedelta(hours=overdue_hours)
        created_at = target_due - timedelta(hours=priority.sla_hours)
        created_at = max(created_at, end_cap - timedelta(days=21))
        created_at = max(created_at, start_cap)

        due_at = created_at + timedelta(hours=priority.sla_hours)
        if due_at < end_cap:
            self.sla_counters["open_breach"] += 1

        return created_at

    def _create_audit_trail(self, *, ticket, created_at, resolved_at, closed_at, actor):
        """Genera auditorías y comentarios en la línea de tiempo del ticket."""

        create_log = AuditLog.objects.create(ticket=ticket, actor=actor, action="CREATE", meta={"auto": True})
        AuditLog.objects.filter(pk=create_log.pk).update(created_at=created_at)

        events_end = closed_at or resolved_at or created_at + timedelta(hours=random.uniform(2, 24))
        comment_logs = random.randint(1, 3) if events_end != created_at else 1
        latest = created_at
        for _ in range(comment_logs):
            offset_hours = random.uniform(0.1, max((events_end - created_at).total_seconds() / 3600, 1))
            event_time = created_at + timedelta(hours=offset_hours)
            event_time = min(event_time, events_end)
            log = AuditLog.objects.create(
                ticket=ticket,
                actor=actor,
                action="COMMENT",
                meta={"auto": True},
            )
            AuditLog.objects.filter(pk=log.pk).update(created_at=event_time)
            latest = max(latest, event_time)

            if random.random() < 0.4:
                comment = TicketComment.objects.create(
                    ticket=ticket,
                    author=actor,
                    body="Seguimiento automático del ticket demo",
                    is_internal=random.random() < 0.5,
                )
                TicketComment.objects.filter(pk=comment.pk).update(created_at=event_time)

        if random.random() < 0.4:
            status_time = created_at + timedelta(hours=random.uniform(0.2, max((events_end - created_at).total_seconds() / 3600, 1)))
            status_time = min(status_time, events_end)
            status_log = AuditLog.objects.create(
                ticket=ticket, actor=actor, action="STATUS", meta={"to": Ticket.IN_PROGRESS}
            )
            AuditLog.objects.filter(pk=status_log.pk).update(created_at=status_time)
            latest = max(latest, status_time)

        if closed_at:
            status_log = AuditLog.objects.create(ticket=ticket, actor=actor, action="STATUS", meta={"to": Ticket.CLOSED})
            AuditLog.objects.filter(pk=status_log.pk).update(created_at=closed_at)
            latest = max(latest, closed_at)
        elif resolved_at:
            status_log = AuditLog.objects.create(ticket=ticket, actor=actor, action="STATUS", meta={"to": Ticket.RESOLVED})
            AuditLog.objects.filter(pk=status_log.pk).update(created_at=resolved_at)
            latest = max(latest, resolved_at)

        return latest

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
                "created_offset_hours": random.uniform(2, 18),
            },
            {
                "title": "Escalamiento ejecutivo por canal digital",
                "category": cat_index.get("SOPORTE AL CLIENTE"),
                "subcategory": Subcategory.objects.filter(name="CHAT").first(),
                "priority": priority_index.get("ALTA"),
                "area": area_index.get("EXPERIENCIA CLIENTE"),
                "status": Ticket.OPEN,
                "requester": critical_requester,
                "created_offset_hours": random.uniform(6, 36),
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
            {
                "title": "Mantenimiento de red multisede completado",
                "category": cat_index.get("INFRAESTRUCTURA"),
                "subcategory": Subcategory.objects.filter(name="WIFI").first(),
                "priority": priority_index.get("BAJA"),
                "area": area_index.get("OPERACIONES"),
                "status": Ticket.RESOLVED,
                "requester": random.choice(requesters),
                "created_offset_hours": 60,
            },
            {
                "title": "Cierre de incidente crítico en sede norte",
                "category": cat_index.get("SEGURIDAD"),
                "subcategory": Subcategory.objects.filter(name="RESPUESTA INCIDENTES").first(),
                "priority": priority_index.get("CRÍTICA"),
                "area": area_index.get("DIRECCIÓN EJECUTIVA"),
                "status": Ticket.CLOSED,
                "requester": random.choice(requesters),
                "created_offset_hours": 36,
            },
        ]

    def _create_featured_tickets(self, *, templates, areas, categories, priorities, requesters, tech_cycle, admins):
        tz = timezone.get_current_timezone()
        end_cap = timezone.make_aware(
            datetime(self.end_date.year, self.end_date.month, self.end_date.day, 23, 59, 59), tz
        )
        start_cap = timezone.make_aware(
            datetime(self.start_date.year, self.start_date.month, self.start_date.day, 0, 0, 0), tz
        )
        tickets = []
        for spec in templates:
            status = spec.get("status", Ticket.OPEN)
            priority_obj = spec.get("priority") or random.choice(priorities)
            created_at = end_cap - timedelta(hours=spec.get("created_offset_hours", 6))
            if status in (Ticket.OPEN, Ticket.IN_PROGRESS):
                created_at = self._maybe_mark_open_overdue(
                    created_at=created_at,
                    priority=priority_obj,
                    end_cap=end_cap,
                    start_cap=start_cap,
                )
            status = self._enforce_status_recency(
                status=status,
                created_at=created_at,
                end_cap=end_cap,
                priority=priority_obj,
            )

            ticket = Ticket.objects.create(
                code="",
                title=spec["title"],
                description="Ticket destacado para validar reglas de SLA y criticidad.",
                requester=spec["requester"],
                category=spec.get("category") or random.choice(categories),
                subcategory=spec.get("subcategory"),
                priority=priority_obj,
                area=spec.get("area") or random.choice(areas),
                status=status,
                kind=Ticket.INCIDENT,
            )
            auto_prob = self._auto_assign_probability(created_at, end_cap)
            auto_flag = random.random() < auto_prob
            auto_assigned, assignment_time = self._normalize_auto_assignment(ticket, created_at, force=auto_flag)
            if not auto_assigned:
                strategy = self._pick_assignment_strategy(created_at=created_at, end_cap=end_cap)
                if strategy == "MANUAL_ASSIGN":
                    admin_actor = random.choice(admins)
                    self._assign_ticket(
                        ticket,
                        to_user=next(tech_cycle),
                        created_at=created_at,
                        actor=admin_actor,
                        reason="MANUAL_ASSIGN",
                    )
                    assignment_time = created_at
                elif strategy == "TECH_SELF_ASSIGN":
                    tech = next(tech_cycle)
                    self._assign_ticket(
                        ticket,
                        to_user=tech,
                        created_at=created_at,
                        actor=tech,
                        reason="TECH_SELF_ASSIGN",
                    )
                    assignment_time = created_at
                else:
                    assignment_time = None

            resolved_at, closed_at = self._build_resolution_timestamps(
                status=status,
                created_at=created_at,
                priority=priority_obj,
                end_cap=end_cap,
            )

            last_assignment_at = assignment_time or created_at
            last_assignment_at = self._maybe_reassign(
                ticket=ticket,
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                tech_cycle=tech_cycle,
                admins=admins,
            )

            audit_latest = self._create_audit_trail(
                ticket=ticket,
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                actor=spec["requester"],
            )
            updated_at_candidates = [created_at, resolved_at, closed_at, audit_latest, last_assignment_at]
            updated_at = max([dt for dt in updated_at_candidates if dt]) if any(updated_at_candidates) else created_at

            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=created_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                updated_at=updated_at,
            )
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

        audit = AuditLog.objects.create(
            ticket=ticket,
            actor=actor or to_user,
            action="ASSIGN",
            meta={
                "to": to_user.id,
                "to_username": to_user.username,
                "from": previous.id if previous else None,
                "from_username": previous.username if previous else None,
                "reason": reason,
            },
        )
        AuditLog.objects.filter(pk=audit.pk).update(created_at=created_at)

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

    def _build_requester_weights(self, requesters):
        """Genera pesos para que ~20% de requesters concentren ~60% de los tickets."""

        total = len(requesters)
        heavy_count = max(1, int(total * 0.2))
        heavy_weight = (0.6 * (total - heavy_count)) / (0.4 * heavy_count)
        heavy_weight = max(3.5, min(heavy_weight, 8.0))

        heavy_indexes = set(random.sample(range(total), k=heavy_count))
        weights = [heavy_weight if idx in heavy_indexes else 1.0 for idx in range(total)]
        return weights

    def _demo_usernames(self):
        base_requesters, extra_first_names, _ = self._requester_seed_data()
        requester_usernames = [username for username, *_ in base_requesters]
        total_requesters = 800
        for idx in range(total_requesters - len(base_requesters)):
            first = extra_first_names[idx % len(extra_first_names)]
            requester_usernames.append(f"req_{first.lower()}_{idx + 1:03d}")

        return [
            "admin_ana",
            "admin_bruno",
            "admin_carla",
            *(f"admin_ext_{idx:02d}" for idx in range(1, 6)),
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
            *(f"tech_ext_{idx:02d}" for idx in range(1, 11)),
            *requester_usernames,
        ]
