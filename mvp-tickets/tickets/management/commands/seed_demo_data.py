from __future__ import annotations

import random
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Iterable, List, Tuple

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.roles import ROLE_ADMIN, ROLE_REQUESTER, ROLE_TECH
from catalog.models import Area, Category, Priority, Subcategory
from tickets.models import (
    AuditLog,
    AutoAssignRule,
    EventLog,
    FAQ,
    Notification,
    Ticket,
    TicketAttachment,
    TicketAssignment,
    TicketComment,
)
from tickets.services import apply_auto_assign

User = get_user_model()


class Command(BaseCommand):
    help = "Genera datos demo coherentes para pruebas y demos (tickets, usuarios, FAQs)."

    def add_arguments(self, parser):
        parser.add_argument("--from-date", dest="from_date", default="2025-01-01")
        parser.add_argument("--to-date", dest="to_date", default=None)
        parser.add_argument("--tickets", type=int, default=1500)
        parser.add_argument("--requesters", type=int, default=150)
        parser.add_argument("--techs", type=int, default=6)
        parser.add_argument("--admins", type=int, default=2)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--flush", action="store_true", help="Borra datos demo generados previamente")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(options["seed"])

        from_date = self._parse_date(options["from_date"], default=date(2025, 1, 1))
        to_date = self._parse_date(options["to_date"], default=timezone.now().date())
        if from_date > to_date:
            raise SystemExit("--from-date no puede ser mayor a --to-date")

        self.stdout.write(self.style.WARNING("Inicializando roles base (init_rbac)..."))
        call_command("init_rbac")

        if options.get("flush"):
            self._flush_demo_data()

        priorities = self._ensure_priorities()
        areas = self._ensure_areas()
        categories = self._ensure_categories()

        admins, techs, requesters = self._ensure_users(
            admin_count=options["admins"],
            tech_count=options["techs"],
            requester_count=options["requesters"],
            areas=areas,
        )

        auto_rules = self._ensure_auto_assign_rules(categories, areas, techs)
        faqs = self._ensure_faqs(categories, techs or admins or requesters)

        # Control para limitar tickets creados el día actual
        self._today_creation_cap = 7
        self._today_creations = 0

        tickets = self._create_tickets(
            total=options["tickets"],
            from_date=from_date,
            to_date=to_date,
            priorities=priorities,
            areas=areas,
            categories=categories,
            requesters=requesters,
            techs=techs,
            admins=admins,
        )

        self._print_summary(admins, techs, requesters, tickets, faqs, auto_rules)

    def _parse_date(self, value: str | None, default: date) -> date:
        if not value:
            return default
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("Formato de fecha inválido, use YYYY-MM-DD")

    # ------------------------------------------------------------------
    # Flush helpers
    # ------------------------------------------------------------------
    def _flush_demo_data(self):
        self.stdout.write(self.style.WARNING("Eliminando datos demo previos..."))
        demo_users = User.objects.filter(username__startswith="demo_").exclude(is_superuser=True)
        demo_ticket_ids = list(Ticket.objects.filter(requester__in=demo_users).values_list("id", flat=True))

        Ticket.objects.filter(id__in=demo_ticket_ids).delete()
        EventLog.objects.filter(actor__in=demo_users).delete()
        if demo_ticket_ids:
            EventLog.objects.filter(model="Ticket", obj_id__in=demo_ticket_ids).delete()
        Notification.objects.filter(user__in=demo_users).delete()
        AutoAssignRule.objects.filter(tech__in=demo_users).delete()
        FAQ.objects.filter(created_by__in=demo_users).delete()

        # El borrado de usuarios en cascada elimina comentarios, adjuntos y logs
        demo_users.delete()

    # ------------------------------------------------------------------
    # Catálogos
    # ------------------------------------------------------------------
    def _ensure_priorities(self) -> List[Priority]:
        payload = [
            ("Baja", 72),
            ("Media", 24),
            ("Alta", 8),
            ("Crítica", 4),
        ]
        priorities = []
        for name, hours in payload:
            obj, _ = Priority.objects.update_or_create(name=name, defaults={"sla_hours": hours})
            priorities.append(obj)
        return priorities

    def _ensure_areas(self) -> List[Area]:
        payload = [
            ("Operaciones", False),
            ("Tecnología", False),
            ("Dirección Ejecutiva", True),
            ("Finanzas", False),
            ("Experiencia Cliente", True),
            ("Riesgo y Continuidad", True),
            ("Recursos Humanos", False),
        ]
        areas = []
        for name, is_critical in payload:
            obj, _ = Area.objects.update_or_create(name=name, defaults={"is_critical": is_critical})
            areas.append(obj)
        return areas

    def _ensure_categories(self) -> List[Category]:
        payload: List[Tuple[str, List[str], str]] = [
            (
                "Soporte Aplicaciones",
                ["ERP", "CRM", "Pagos", "API Partners"],
                "Fallos funcionales y mejoras en sistemas de negocio.",
            ),
            (
                "Infraestructura",
                ["VPN", "Wifi", "Correo", "Almacenamiento"],
                "Redes, accesos y servicios de conectividad.",
            ),
            (
                "Seguridad",
                ["Credenciales", "MFA", "Alertas SIEM", "Respuesta incidentes"],
                "Gestión de identidades y alertas de seguridad.",
            ),
            (
                "Dispositivos",
                ["Laptop", "Impresora", "Periféricos", "Móviles"],
                "Hardware de usuario final.",
            ),
            (
                "Datos y Analítica",
                ["ETL", "Reporting", "Dashboards"],
                "Pipelines, consultas y modelos de datos corporativos.",
            ),
            (
                "Soporte al Cliente",
                ["Telefonía", "Chat", "Herramientas de campo"],
                "Continuidad de las herramientas de experiencia cliente.",
            ),
        ]
        categories: List[Category] = []
        for name, subs, description in payload:
            cat, _ = Category.objects.update_or_create(
                name=name, defaults={"description": description, "is_active": True}
            )
            categories.append(cat)
            for sub in subs:
                Subcategory.objects.update_or_create(
                    category=cat,
                    name=sub,
                    defaults={"description": f"Subcategoría {sub.title()}", "is_active": True},
                )
        return categories

    # ------------------------------------------------------------------
    # Usuarios
    # ------------------------------------------------------------------
    def _ensure_users(self, *, admin_count: int, tech_count: int, requester_count: int, areas: List[Area]):
        admin_group = Group.objects.get(name=ROLE_ADMIN)
        tech_group = Group.objects.get(name=ROLE_TECH)
        requester_group = Group.objects.get(name=ROLE_REQUESTER)

        demo_password = "Demo1234!"
        first_names = [
            "Ana",
            "Bruno",
            "Camila",
            "Diego",
            "Elena",
            "Fabio",
            "Gabriela",
            "Hugo",
            "Isabel",
            "Javier",
            "Karen",
            "Luis",
            "Marta",
            "Nicolás",
            "Olga",
            "Pablo",
            "Quintín",
            "Rocío",
            "Sofía",
            "Tomás",
            "Úrsula",
            "Valentina",
            "Walter",
            "Ximena",
            "Yolanda",
            "Zoe",
        ]
        last_names = [
            "Pérez",
            "Salas",
            "Mena",
            "Ramos",
            "Flores",
            "Aguilar",
            "Valdés",
            "Rivas",
            "Campos",
            "González",
            "Ibáñez",
            "Jara",
            "Lagos",
            "Morales",
            "Navarro",
            "Osses",
            "Ponce",
            "Quiroga",
            "Romero",
            "Saavedra",
            "Tapia",
            "Ugarte",
            "Vidal",
            "Zapata",
        ]

        def pick_name(idx: int) -> Tuple[str, str]:
            return first_names[idx % len(first_names)], last_names[idx % len(last_names)]

        def build_user(prefix: str, idx: int, group: Group, *, is_staff=False, area=None, critical=False):
            username = f"demo_{prefix}_{idx+1:02d}"
            first, last = pick_name(idx)
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@demo.local",
                    "first_name": first,
                    "last_name": last,
                    "is_staff": is_staff,
                },
            )
            if not user.is_staff and is_staff:
                user.is_staff = True
            user.first_name = user.first_name or first
            user.last_name = user.last_name or last
            user.email = user.email or f"{username}@demo.local"
            user.set_password(demo_password)
            user.save()
            user.groups.add(group)

            profile = getattr(user, "profile", None)
            if profile:
                profile.area = profile.area or area
                profile.is_critical_actor = profile.is_critical_actor or critical
                profile.save(update_fields=["area", "is_critical_actor"])
            return user

        admins = [build_user("admin", i, admin_group, is_staff=True, area=random.choice(areas), critical=i == 0) for i in range(admin_count)]
        techs = [build_user("tech", i, tech_group, area=random.choice(areas), critical=i < 2) for i in range(tech_count)]
        requesters = [build_user("req", i, requester_group, area=random.choice(areas), critical=i % 10 == 0) for i in range(requester_count)]

        return admins, techs, requesters

    # ------------------------------------------------------------------
    # Autoasignación y FAQs
    # ------------------------------------------------------------------
    def _ensure_auto_assign_rules(self, categories: List[Category], areas: List[Area], techs: List[User]):
        if not techs:
            return []
        rules = []
        cat_index = {c.name.lower(): c for c in categories}
        area_index = {a.name.lower(): a for a in areas}
        primary_tech = techs[0]
        backup_tech = techs[1] if len(techs) > 1 else techs[0]

        rule_specs = [
            {"category": cat_index.get("infraestructura"), "subcategory_name": "VPN", "tech": primary_tech},
            {"category": cat_index.get("seguridad"), "subcategory_name": "Credenciales", "tech": backup_tech},
            {"category": cat_index.get("soporte aplicaciones"), "subcategory_name": "ERP", "tech": primary_tech},
            {"category": cat_index.get("datos y analítica"), "subcategory_name": "Reporting", "tech": backup_tech},
            {
                "category": cat_index.get("soporte al cliente"),
                "area": area_index.get("experiencia cliente"),
                "tech": primary_tech,
            },
            {"area": area_index.get("riesgo y continuidad"), "tech": backup_tech},
        ]
        for spec in rule_specs:
            sub = None
            if spec.get("subcategory_name"):
                sub = Subcategory.objects.filter(name__iexact=spec["subcategory_name"], category=spec.get("category")).first()
            rule, _ = AutoAssignRule.objects.update_or_create(
                category=spec.get("category"),
                subcategory=sub,
                area=spec.get("area"),
                defaults={"tech": spec["tech"], "is_active": True},
            )
            rules.append(rule)
        return rules

    def _ensure_faqs(self, categories: List[Category], authors: Iterable[User]):
        authors = list(authors)
        if not authors:
            return []
        author = authors[0]
        cat_index = {c.name.lower(): c for c in categories}
        payload = [
            (
                "¿Cómo resetear mi contraseña?",
                "Utiliza el portal de autoservicio y confirma con MFA.",
                "Seguridad",
                "Credenciales",
            ),
            (
                "Conexión VPN inestable",
                "Valida tu cliente, renueva certificados desde el portal interno y reinicia el equipo.",
                "Infraestructura",
                "VPN",
            ),
            (
                "Solicitar acceso temporal a un sistema",
                "Crea el ticket indicando sistema, responsable aprobador y fecha de caducidad.",
                "Soporte Aplicaciones",
                "ERP",
            ),
            (
                "Buenas prácticas para comentar tickets",
                "Describe el impacto, pasos ejecutados y próximos hitos; evita adjuntar datos sensibles.",
                "Soporte Aplicaciones",
                "API Partners",
            ),
            (
                "Impresora sin responder",
                "Revisa conexión de red, reinicia el equipo y comparte el código del activo.",
                "Dispositivos",
                "Impresora",
            ),
            (
                "Reportes atrasados en BI",
                "Confirma si hubo cargas nocturnas fallidas y adjunta el dashboard o consulta afectada.",
                "Datos y Analítica",
                "Reporting",
            ),
        ]
        faqs = []
        for question, answer, cat_name, sub_name in payload:
            faq, _ = FAQ.objects.get_or_create(
                question=question,
                defaults={
                    "answer": answer,
                    "category": cat_index.get(cat_name.lower()),
                    "subcategory": Subcategory.objects.filter(name__iexact=sub_name).first(),
                    "created_by": author,
                    "updated_by": author,
                },
            )
            if faq.video_url:
                faq.video_url = ""
                faq.save(update_fields=["video_url"])
            if faq.image:
                faq.image.delete(save=True)
            faqs.append(faq)
        return faqs

    # ------------------------------------------------------------------
    # Tickets y actividad
    # ------------------------------------------------------------------
    def _build_status_plan(self, total: int) -> List[str]:
        proportions = [
            (Ticket.CLOSED, 0.58),
            (Ticket.RESOLVED, 0.22),
            (Ticket.IN_PROGRESS, 0.15),
            (Ticket.OPEN, 0.05),
        ]
        plan: List[str] = []
        for status, pct in proportions:
            plan.extend([status] * int(total * pct))
        while len(plan) < total:
            plan.append(Ticket.IN_PROGRESS if len(plan) % 2 else Ticket.CLOSED)
        random.shuffle(plan)
        return plan[:total]

    def _pick_created_at(self, *, status: str, from_date: date, to_date: date) -> datetime:
        end_dt = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))
        start_dt = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
        if status in (Ticket.OPEN, Ticket.IN_PROGRESS):
            recent_start = max(start_dt, end_dt - timedelta(days=20))
            delta = end_dt - recent_start
            created_at = recent_start + timedelta(seconds=random.uniform(0, delta.total_seconds()))
        else:
            span = (end_dt - start_dt).total_seconds()
            created_at = start_dt + timedelta(seconds=random.uniform(0, span * 0.85))
        if created_at > end_dt:
            created_at = end_dt - timedelta(hours=random.uniform(1, 6))

        if created_at.date() == to_date:
            if self._today_creations >= self._today_creation_cap:
                created_at = created_at - timedelta(days=random.randint(1, 5))
            else:
                self._today_creations += 1
        return created_at

    def _pick_resolution_times(self, *, status: str, created_at: datetime, priority: Priority, to_date: date):
        end_dt = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))
        resolved_at = None
        closed_at = None
        if status in (Ticket.RESOLVED, Ticket.CLOSED):
            factor = random.uniform(0.5, 1.15)
            resolved_at = created_at + timedelta(hours=priority.sla_hours * factor)
            if resolved_at > end_dt:
                resolved_at = end_dt - timedelta(hours=random.uniform(1, 6))
        if status == Ticket.CLOSED:
            closed_at = (resolved_at or created_at) + timedelta(hours=random.uniform(2, 24))
            if closed_at > end_dt:
                closed_at = end_dt - timedelta(hours=random.uniform(1, 6))
        return resolved_at, closed_at

    def _build_title(self, *, category: Category, subcategory: Subcategory | None, idx: int) -> str:
        catalog = {
            "infraestructura": [
                "Incidente de VPN: desconexiones recurrentes",
                "Correo corporativo sin sincronizar",
                "Alerta de ancho de banda en sede principal",
            ],
            "seguridad": [
                "Bloqueo de MFA para usuario",
                "Solicitud de restablecimiento de credenciales privilegiadas",
                "Investigación de alerta SIEM",
            ],
            "soporte aplicaciones": [
                "Error al aprobar orden en ERP",
                "Integración con CRM devuelve timeout",
                "Mejora menor en flujo de API Partners",
            ],
            "dispositivos": [
                "Laptop con rendimiento degradado",
                "Teclado inalámbrico sin respuesta",
                "Solicitud de periférico de reemplazo",
            ],
            "datos y analítica": [
                "ETL nocturna falló por falta de espacio",
                "Dashboard sin refrescar métricas diarias",
            ],
            "soporte al cliente": [
                "Cortes en telefonía de sucursal",
                "Chat de agentes no recibe nuevos casos",
            ],
        }
        pool = catalog.get(category.name.lower(), [])
        if subcategory:
            pool.append(f"Seguimiento por {subcategory.name.title()}")
        if not pool:
            return f"Seguimiento operativo #{idx:04d}"
        return random.choice(pool)

    def _create_tickets(
        self,
        *,
        total: int,
        from_date: date,
        to_date: date,
        priorities: List[Priority],
        areas: List[Area],
        categories: List[Category],
        requesters: List[User],
        techs: List[User],
        admins: List[User],
    ) -> List[Ticket]:
        status_plan = self._build_status_plan(total)
        tickets: List[Ticket] = []
        notifications: List[Notification] = []

        category_weights = {c.name.lower(): 2 for c in categories}
        for name in ["infraestructura", "seguridad"]:
            if name in category_weights:
                category_weights[name] += 2

        tech_weights = [3 if idx < 2 else 1 for idx, _ in enumerate(techs)] or [1]

        for idx, status in enumerate(status_plan, start=1):
            requester = random.choice(requesters)
            category = random.choices(categories, weights=[category_weights.get(c.name.lower(), 1) for c in categories])[0]
            sub_qs = list(category.subcategories.all()) or list(Subcategory.objects.filter(category=category))
            subcategory = random.choice(sub_qs) if sub_qs else None
            priority = random.choices(priorities, weights=[2, 3, 3, 1])[0]
            area = random.choice(areas)

            created_at = self._pick_created_at(status=status, from_date=from_date, to_date=to_date)
            resolved_at, closed_at = self._pick_resolution_times(status=status, created_at=created_at, priority=priority, to_date=to_date)

            ticket = Ticket.objects.create(
                code="",
                title=self._build_title(category=category, subcategory=subcategory, idx=idx),
                description=(
                    f"Ticket generado para escenarios de tablero y SLA. Prioridad {priority.name}. "
                    f"Solicitante del área {getattr(getattr(requester, 'profile', None), 'area', area).name if getattr(getattr(requester, 'profile', None), 'area', None) else area.name}."
                ),
                requester=requester,
                category=category,
                subcategory=subcategory,
                priority=priority,
                area=area,
                status=status,
                kind=Ticket.INCIDENT if idx % 4 == 0 else Ticket.REQUEST,
            )

            Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at, resolved_at=resolved_at, closed_at=closed_at)
            ticket.created_at = created_at
            ticket.resolved_at = resolved_at
            ticket.closed_at = closed_at

            create_log = AuditLog.objects.create(
                ticket=ticket,
                actor=requester,
                action="CREATE",
                meta={"source": "seed_demo_data"},
            )
            AuditLog.objects.filter(pk=create_log.pk).update(
                created_at=created_at + timedelta(minutes=random.uniform(1, 8))
            )

            auto_assigned = apply_auto_assign(ticket, actor=requester)
            if not auto_assigned:
                chosen_tech = random.choices(techs, weights=tech_weights, k=1)[0] if techs else None
                if chosen_tech:
                    assignment = TicketAssignment.objects.create(
                        ticket=ticket,
                        from_user=requester,
                        to_user=chosen_tech,
                        reason="distribución demo",
                    )
                    TicketAssignment.objects.filter(pk=assignment.pk).update(created_at=created_at + timedelta(minutes=5))
                    ticket.assigned_to = chosen_tech
                    ticket.save(update_fields=["assigned_to", "updated_at"])
                    AuditLog.objects.create(
                        ticket=ticket,
                        actor=requester,
                        action="ASSIGN",
                        meta={"to": chosen_tech.id, "to_username": chosen_tech.username, "reason": "distribución"},
                    )

            if auto_assigned:
                latest_assignment = (
                    TicketAssignment.objects.filter(ticket=ticket).order_by("-created_at").first()
                )
                if latest_assignment:
                    TicketAssignment.objects.filter(pk=latest_assignment.pk).update(
                        created_at=created_at + timedelta(minutes=random.uniform(6, 15))
                    )
                auto_log = (
                    AuditLog.objects.filter(ticket=ticket, action="ASSIGN").order_by("-created_at").first()
                )
                if auto_log:
                    AuditLog.objects.filter(pk=auto_log.pk).update(
                        created_at=created_at + timedelta(minutes=random.uniform(6, 15))
                    )

            if status != Ticket.OPEN:
                status_actor = random.choice(techs) if techs else None
                status_log = AuditLog.objects.create(
                    ticket=ticket,
                    actor=status_actor,
                    action="STATUS",
                    meta={"new_status": status},
                )
                AuditLog.objects.filter(pk=status_log.pk).update(
                    created_at=(resolved_at or created_at) - timedelta(minutes=random.uniform(15, 45))
                    if resolved_at
                    else created_at + timedelta(minutes=random.uniform(30, 90))
                )

            if techs and random.random() < 0.18 and len(techs) > 1:
                reassigned_to = random.choice([t for t in techs if t != ticket.assigned_to])
                if reassigned_to:
                    reassign_time = created_at + timedelta(minutes=random.uniform(25, 240))
                    reassign = TicketAssignment.objects.create(
                        ticket=ticket,
                        from_user=ticket.assigned_to,
                        to_user=reassigned_to,
                        reason="reasignación por disponibilidad",
                    )
                    TicketAssignment.objects.filter(pk=reassign.pk).update(created_at=reassign_time)
                    ticket.assigned_to = reassigned_to
                    ticket.save(update_fields=["assigned_to", "updated_at"])
                    reassign_log = AuditLog.objects.create(
                        ticket=ticket,
                        actor=status_actor or requester,
                        action="ASSIGN",
                        meta={
                            "from": getattr(reassign.from_user, "id", None),
                            "from_username": getattr(reassign.from_user, "username", None),
                            "to": reassigned_to.id,
                            "to_username": reassigned_to.username,
                            "reason": "reasignación",
                        },
                    )
                    AuditLog.objects.filter(pk=reassign_log.pk).update(created_at=reassign_time)

            self._maybe_add_interactions(ticket=ticket, created_at=created_at, resolved_at=resolved_at, techs=techs, admins=admins)

            if self._is_critical_ticket(ticket):
                recipients = list({*techs, *admins})
                for user in recipients:
                    notifications.append(
                        Notification(
                            user=user,
                            message=f"Ticket crítico {ticket.code or ticket.id} creado: {ticket.title}",
                            url=f"/tickets/{ticket.pk}/",
                            created_at=created_at,
                        )
                    )
                critic_actor = random.choice(recipients) if recipients else None
                event = EventLog.objects.create(
                    actor=critic_actor,
                    model="Ticket",
                    obj_id=ticket.pk,
                    action="ALERTA",
                    message="Ticket crítico generado por seed_demo_data",
                    resource_id=ticket.pk,
                )
                EventLog.objects.filter(pk=event.pk).update(
                    created_at=created_at + timedelta(minutes=random.uniform(1, 10))
                )

            tickets.append(ticket)

        if notifications:
            Notification.objects.bulk_create(notifications)
        return tickets

    def _maybe_add_interactions(self, *, ticket: Ticket, created_at: datetime, resolved_at: datetime | None, techs: List[User], admins: List[User]):
        # Comentarios
        if random.random() < 0.75:
            author_pool = techs + admins
            author = random.choice(author_pool) if author_pool else ticket.requester
            comment_time = created_at + timedelta(hours=random.uniform(1, 6))
            comment = TicketComment.objects.create(
                ticket=ticket,
                author=author,
                body="Seguimiento automático para validar hilos de conversación.",
            )
            TicketComment.objects.filter(pk=comment.pk).update(created_at=comment_time)
            AuditLog.objects.create(ticket=ticket, actor=author, action="COMMENT", meta={"auto": True})

            if self._is_critical_ticket(ticket) or getattr(author.profile, "is_critical_actor", False):
                recipients = list({*(techs + admins)}) or [ticket.requester]
                notif_body = (
                    f"Nuevo comentario en ticket crítico {ticket.code or ticket.id}: {ticket.title}. "
                    f"Autor: {author.get_full_name() or author.username}"
                )
                notifications = [
                    Notification(user=user, message=notif_body, url=f"/tickets/{ticket.pk}/", created_at=comment_time)
                    for user in recipients
                ]
                Notification.objects.bulk_create(notifications)

        # Adjuntos
        if random.random() < 0.25:
            uploader = random.choice(techs) if techs else ticket.requester
            attachment = TicketAttachment.objects.create(
                ticket=ticket,
                uploaded_by=uploader,
                file=ContentFile(b"demo", name=f"evidencia_{ticket.pk}.txt"),
                content_type="text/plain",
                size=4,
            )
            TicketAttachment.objects.filter(pk=attachment.pk).update(uploaded_at=created_at + timedelta(hours=3))
            AuditLog.objects.create(ticket=ticket, actor=uploader, action="ATTACH", meta={"filename": attachment.file.name})

        # Evento de cierre/resolución
        if resolved_at:
            closer = random.choice(techs) if techs else None
            AuditLog.objects.create(
                ticket=ticket,
                actor=closer,
                action="UPDATE",
                meta={"resolved_at": resolved_at.isoformat()},
            )
            if ticket.status == Ticket.CLOSED:
                close_event = EventLog.objects.create(
                    actor=closer,
                    model="Ticket",
                    obj_id=ticket.pk,
                    action="CIERRE",
                    message="Ticket cerrado durante seed_demo_data",
                    resource_id=ticket.pk,
                )
                EventLog.objects.filter(pk=close_event.pk).update(
                    created_at=(ticket.closed_at or resolved_at or created_at)
                )

    def _is_critical_ticket(self, ticket: Ticket) -> bool:
        priority_name = (ticket.priority.name or "").lower()
        return priority_name.startswith("crít") or (ticket.area and ticket.area.is_critical) or getattr(ticket.requester, "is_critical_actor", False)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _print_summary(self, admins: List[User], techs: List[User], requesters: List[User], tickets: List[Ticket], faqs: List[FAQ], rules: List[AutoAssignRule]):
        counts = Counter([t.status for t in tickets])
        top_techs = (
            User.objects.filter(id__in=[u.id for u in techs])
            .annotate(closed=Count("assigned", filter=Q(assigned__status__in=[Ticket.CLOSED, Ticket.RESOLVED])))
            .order_by("-closed")[:5]
        )

        self.stdout.write(self.style.SUCCESS("Dataset demo generado"))
        self.stdout.write(self.style.NOTICE(f"Admins: {len(admins)} | Técnicos: {len(techs)} | Solicitantes: {len(requesters)}"))
        self.stdout.write(
            self.style.NOTICE(
                f"Tickets: {len(tickets)} | Abiertos: {counts[Ticket.OPEN]} | En progreso: {counts[Ticket.IN_PROGRESS]} | "
                f"Resueltos: {counts[Ticket.RESOLVED]} | Cerrados: {counts[Ticket.CLOSED]}"
            )
        )
        self.stdout.write(self.style.NOTICE(f"FAQs creadas: {len(faqs)} | Reglas de autoasignación: {len(rules)}"))
        self.stdout.write(self.style.SUCCESS("Top técnicos por tickets cerrados/resueltos:"))
        for tech in top_techs:
            self.stdout.write(f" - {tech.username}: {tech.closed} tickets")
