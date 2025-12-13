"""
Crea un dataset de demostración rico en tickets, catálogos, usuarios y reglas.

- Ejecuta ``python manage.py load_demo_dataset --purge`` para borrar datos previos
  (tickets, catálogos demo y usuarios de prueba) y volver a generar todo.
 - Genera por defecto un escenario multi-sede con 6000 tickets variados,
   categorías, subcategorías, prioridades, áreas, FAQs y reglas de autoasignación activas.
"""

from __future__ import annotations

import random
from calendar import monthrange
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
            default=6000,
            help="Cantidad de tickets a generar (por defecto: 6000).",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Elimina tickets, catálogos demo, FAQs y usuarios de prueba antes de crear el dataset.",
        )
        parser.add_argument(
            "--requesters",
            type=int,
            default=500,
            help="Cantidad de usuarios solicitantes a generar (por defecto: 500).",
        )
        parser.add_argument(
            "--techs",
            type=int,
            default=10,
            help="Cantidad de técnicos resolutores (por defecto: 10).",
        )
        parser.add_argument(
            "--admins",
            type=int,
            default=3,
            help="Cantidad de administradores (por defecto: 3).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        total_tickets = max(2050, min(options["tickets"], 9110))
        purge = options["purge"]
        total_requesters = max(300, min(options["requesters"], 800))
        total_techs = max(6, min(options["techs"], 15))
        total_admins = max(2, min(options["admins"], 4))

        self.auto_assign_rate = random.uniform(0.5, 0.6)
        manual_target = random.uniform(0.25, 0.35)
        self_target = random.uniform(0.05, 0.1)
        remaining = max(1 - self.auto_assign_rate, 0.05)
        manual_conditional = manual_target / remaining
        self_conditional = self_target / remaining
        normalization = manual_conditional + self_conditional
        if normalization > 0.95:
            factor = 0.95 / normalization
            manual_conditional *= factor
            self_conditional *= factor

        self.manual_assign_rate = manual_conditional
        self.self_assign_rate = self_conditional
        self.reassign_rate = random.uniform(0.1, 0.2)

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
        end_cap = timezone.make_aware(datetime(2025, 12, 12, 23, 59, 59), tz)
        created_schedule = self._build_created_at_schedule(total, tz)

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

            if status in (Ticket.OPEN, Ticket.IN_PROGRESS) and random.random() < random.uniform(0.0, 0.03):
                created_at = max(
                    created_at - timedelta(hours=priority.sla_hours * random.uniform(1.1, 2.0)),
                    timezone.make_aware(datetime(2025, 1, 1, 0, 0), tz),
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

            auto_flag = random.random() < self.auto_assign_rate
            auto_assigned, assignment_time = self._normalize_auto_assignment(ticket, created_at, force=auto_flag)

            chosen_tech = next(tech_cycle)
            if not auto_assigned:
                strategy = self._pick_assignment_strategy()
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
                tz=tz,
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

    def _build_created_at_schedule(self, total: int, tz):
        """Genera fechas realistas en 2025 priorizando horario laboral y días hábiles."""

        start = timezone.make_aware(datetime(2025, 1, 1, 0, 0), tz)
        end = timezone.make_aware(datetime(2025, 12, 12, 23, 59, 59), tz)
        day_span = (end.date() - start.date()).days

        schedule = []
        december_forced = [
            timezone.make_aware(datetime(2025, 12, 5, 10, 30), tz),
            timezone.make_aware(datetime(2025, 12, 9, 15, 10), tz),
            timezone.make_aware(datetime(2025, 12, 11, 11, 45), tz),
        ]

        for _ in range(total * 2):  # oversampling para seleccionar los mejores slots
            day_offset = random.randint(0, day_span)
            date_candidate = start + timedelta(days=day_offset)
            weekday = date_candidate.weekday()
            is_weekday = weekday < 5
            if not is_weekday and random.random() < 0.8:
                continue

            if random.random() < 0.9:
                hour = random.randint(8, 19)
            else:
                hour = random.randint(0, 23)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            created_at = timezone.make_aware(
                datetime(
                    date_candidate.year,
                    date_candidate.month,
                    date_candidate.day,
                    hour,
                    minute,
                    second,
                ),
                tz,
            )
            if created_at > end:
                created_at = end - timedelta(hours=random.uniform(0.5, 6))
            schedule.append(created_at)

        schedule.extend(december_forced)
        while len(schedule) < total:
            schedule.append(start + timedelta(days=random.randint(0, day_span), hours=random.randint(6, 18)))

        schedule = sorted(schedule)
        forced_set = set(december_forced)
        while len(schedule) > total:
            if schedule[0] in forced_set:
                for idx, dt in enumerate(schedule[1:], start=1):
                    if dt not in forced_set:
                        schedule.pop(idx)
                        break
                else:
                    schedule.pop()
            else:
                schedule.pop(0)
        schedule = schedule[:total]
        return schedule

    def _choose_status_by_age(self, *, created_at, end_cap):
        days_old = (end_cap.date() - created_at.date()).days

        if days_old <= 3:
            choices = [(Ticket.OPEN, 0.35), (Ticket.IN_PROGRESS, 0.35), (Ticket.RESOLVED, 0.18), (Ticket.CLOSED, 0.12)]
        elif days_old <= 7:
            choices = [(Ticket.OPEN, 0.25), (Ticket.IN_PROGRESS, 0.35), (Ticket.RESOLVED, 0.25), (Ticket.CLOSED, 0.15)]
        elif days_old <= 14:
            choices = [(Ticket.OPEN, 0.12), (Ticket.IN_PROGRESS, 0.38), (Ticket.RESOLVED, 0.3), (Ticket.CLOSED, 0.2)]
        elif days_old <= 30:
            choices = [(Ticket.IN_PROGRESS, 0.18), (Ticket.RESOLVED, 0.45), (Ticket.CLOSED, 0.37)]
        elif days_old <= 45:
            choices = [(Ticket.RESOLVED, 0.45), (Ticket.CLOSED, 0.55)]
        else:
            choices = [(Ticket.RESOLVED, 0.2), (Ticket.CLOSED, 0.8)]

        roll = random.random()
        cumulative = 0
        for status, weight in choices:
            cumulative += weight
            if roll <= cumulative:
                return status
        return choices[-1][0]

    def _pick_assignment_strategy(self):
        roll = random.random()
        manual_cutoff = self.manual_assign_rate
        self_cutoff = manual_cutoff + self.self_assign_rate
        if roll < manual_cutoff:
            return "MANUAL_ASSIGN"
        if roll < self_cutoff:
            return "TECH_SELF_ASSIGN"
        return "UNASSIGNED"

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

    def _build_resolution_timestamps(self, *, status, created_at, priority, tz):
        """Crea timestamps de resolución/cierre dentro o fuera de SLA según proporciones."""

        if status not in (Ticket.RESOLVED, Ticket.CLOSED):
            return None, None

        end_cap = timezone.make_aware(datetime(2025, 12, 12, 23, 59, 59), tz)

        within_sla_rate = random.uniform(0.88, 0.95)
        breach_rate = random.uniform(0.05, 0.12)
        out_of_sla = random.random() < breach_rate
        on_time = random.random() < within_sla_rate and not out_of_sla

        if on_time:
            factor = random.uniform(0.6, 0.95)
        elif out_of_sla:
            factor = random.uniform(1.05, 1.8)
        else:
            factor = random.uniform(0.95, 1.2)

        resolved_at = created_at + timedelta(hours=priority.sla_hours * factor)
        if resolved_at < created_at:
            resolved_at = created_at
        if resolved_at > end_cap:
            resolved_at = end_cap - timedelta(hours=random.uniform(0.2, 4))

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
        end_cap = timezone.make_aware(datetime(2025, 12, 12, 23, 59, 59), tz)
        tickets = []
        for spec in templates:
            created_at = end_cap - timedelta(hours=spec.get("created_offset_hours", 6))
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
            auto_flag = random.random() < self.auto_assign_rate
            auto_assigned, assignment_time = self._normalize_auto_assignment(ticket, created_at, force=auto_flag)
            if not auto_assigned:
                strategy = self._pick_assignment_strategy()
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
                status=spec.get("status", Ticket.OPEN),
                created_at=created_at,
                priority=spec.get("priority") or random.choice(priorities),
                tz=tz,
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
