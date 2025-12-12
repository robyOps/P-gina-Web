# mvp-tickets/tickets/management/commands/seed_demo.py
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, date

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from accounts.roles import ROLE_ADMIN, ROLE_REQUESTER, ROLE_TECH


# -----------------------------
# Configuración de realismo
# -----------------------------

@dataclass(frozen=True)
class PrioritySpec:
    name: str
    sla_hours: int


PRIORITIES: list[PrioritySpec] = [
    PrioritySpec("Crítica", 4),
    PrioritySpec("Alta", 8),
    PrioritySpec("Media", 24),
    PrioritySpec("Baja", 72),
]

AREAS = [
    ("Operaciones", True),
    ("Infraestructura TI", True),
    ("Soporte TI", False),
    ("Administración", False),
    ("RRHH", False),
    ("Finanzas", False),
]

CATEGORIES = {
    "Accesos": ["Correo", "VPN", "Cuenta", "Permisos"],
    "Equipos": ["Notebook", "PC", "Impresora", "Periféricos"],
    "Red": ["WiFi", "Cableado", "Switch/Router"],
    "Software": ["Office", "ERP", "Navegador", "Otro"],
    "Incidentes": ["Caída servicio", "Lentitud", "Error crítico"],
}

FAQS = [
    {
        "question": "¿Cómo restablezco mi contraseña?",
        "answer": "Puedes solicitar un restablecimiento desde la opción 'Olvidé mi contraseña' o pedir apoyo a Soporte TI.",
        "image": "faq_password.png",
        "video_url": "",
        "video_file": "",
    },
    {
        "question": "¿Cómo me conecto a la VPN?",
        "answer": "Instala el cliente, usa tus credenciales corporativas y selecciona el perfil 'Coyahue-VPN'.",
        "image": "",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "video_file": "",
    },
    {
        "question": "¿Qué información debo incluir al reportar un incidente?",
        "answer": "Describe qué pasó, desde cuándo ocurre, captura de pantalla si aplica y el impacto en tu trabajo.",
        "image": "",
        "video_url": "",
        "video_file": "",
    },
]


STATUS_OPEN = "OPEN"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_RESOLVED = "RESOLVED"
STATUS_CLOSED = "CLOSED"

KIND_REQUEST = "REQUEST"
KIND_INCIDENT = "INCIDENT"


def aware(dt: datetime) -> datetime:
    """Asegura datetime aware usando timezone actual."""
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def rand_time_on_day(d: date, rng: random.Random) -> datetime:
    """Hora aleatoria (distinta) dentro del día."""
    hour = rng.randint(8, 19)          # horario típico de oficina
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return aware(datetime(d.year, d.month, d.day, hour, minute, second))


def clamp_dt(dt: datetime, end_dt: datetime) -> datetime:
    return dt if dt <= end_dt else end_dt


class Command(BaseCommand):
    help = "Carga datos DEMO realistas (2025-01-01 a 2025-12-12) con logs y SLA coherentes."

    def add_arguments(self, parser):
        parser.add_argument("--tickets", type=int, default=600, help="Cantidad total de tickets a generar.")
        parser.add_argument("--seed", type=int, default=42, help="Seed aleatoria para reproducibilidad.")
        parser.add_argument("--reset", action="store_true", help="Borra datos de tickets (no usuarios/catálogos) y regenera.")
        parser.add_argument("--start", type=str, default="2025-01-01", help="Fecha inicio (YYYY-MM-DD).")
        parser.add_argument("--end", type=str, default="2025-12-12", help="Fecha fin (YYYY-MM-DD).")

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(opts["seed"])
        start = date.fromisoformat(opts["start"])
        end = date.fromisoformat(opts["end"])
        end_dt = aware(datetime(end.year, end.month, end.day, 23, 59, 59))

        # Modelos (robusto: no asumimos imports directos)
        Area = apps.get_model("catalog", "Area")
        Category = apps.get_model("catalog", "Category")
        Subcategory = apps.get_model("catalog", "Subcategory")
        Priority = apps.get_model("catalog", "Priority")

        Ticket = apps.get_model("tickets", "Ticket")
        TicketComment = apps.get_model("tickets", "TicketComment")
        TicketAttachment = apps.get_model("tickets", "TicketAttachment")
        AuditLog = apps.get_model("tickets", "AuditLog")
        EventLog = apps.get_model("tickets", "EventLog")
        Notification = apps.get_model("tickets", "Notification")
        FAQ = apps.get_model("tickets", "FAQ")
        AutoAssignRule = apps.get_model("tickets", "AutoAssignRule")

        # TicketAssignment es opcional según tu proyecto
        TicketAssignment = None
        try:
            TicketAssignment = apps.get_model("tickets", "TicketAssignment")
        except Exception:
            TicketAssignment = None

        UserProfile = apps.get_model("accounts", "UserProfile")
        User = get_user_model()

        # Reset parcial (solo datos de la mesa de ayuda)
        if opts["reset"]:
            self.stdout.write(self.style.WARNING("Reset: borrando datos de tickets/FAQ/autoasignación/logs/notificaciones..."))
            TicketComment.objects.all().delete()
            TicketAttachment.objects.all().delete()
            if TicketAssignment:
                TicketAssignment.objects.all().delete()
            AuditLog.objects.all().delete()
            EventLog.objects.all().delete()
            Notification.objects.all().delete()
            AutoAssignRule.objects.all().delete()
            FAQ.objects.all().delete()
            Ticket.objects.all().delete()

        # Roles / grupos
        from django.contrib.auth.models import Group
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        tech_group, _ = Group.objects.get_or_create(name=ROLE_TECH)
        requester_group, _ = Group.objects.get_or_create(name=ROLE_REQUESTER)

        # Usuarios DEMO (si ya existen, los reutiliza)
        admin = self._get_or_create_user(User, "admin.coyahue", "admin@coyahue.cl", rng, is_staff=True, is_superuser=True)
        techs = [
            self._get_or_create_user(User, f"tecnico{i}", f"tecnico{i}@coyahue.cl", rng, is_staff=True)
            for i in range(1, 6)
        ]
        requesters = [
            self._get_or_create_user(User, f"solicitante{i}", f"solicitante{i}@coyahue.cl", rng, is_staff=False)
            for i in range(1, 26)
        ]

        admin.groups.add(admin_group)
        for t in techs:
            t.groups.add(tech_group)
        for r in requesters:
            r.groups.add(requester_group)

        # Catálogos
        areas = []
        for name, is_critical in AREAS:
            area, _ = Area.objects.get_or_create(name=name, defaults={"is_critical": is_critical})
            # si ya existe, lo actualizamos para asegurar coherencia
            if area.is_critical != is_critical:
                area.is_critical = is_critical
                area.save(update_fields=["is_critical"])
            areas.append(area)

        categories = {}
        subcategories = []
        for cat_name, subs in CATEGORIES.items():
            cat, _ = Category.objects.get_or_create(
                name=cat_name,
                defaults={"description": f"Categoría {cat_name} para mesa de ayuda.", "is_active": True},
            )
            categories[cat_name] = cat
            for sub_name in subs:
                sub, _ = Subcategory.objects.get_or_create(
                    name=sub_name,
                    category=cat,
                    defaults={"description": f"Subcategoría {sub_name}.", "is_active": True},
                )
                subcategories.append(sub)

        priorities = {}
        for spec in PRIORITIES:
            p, _ = Priority.objects.get_or_create(name=spec.name, defaults={"sla_hours": spec.sla_hours})
            if getattr(p, "sla_hours", None) != spec.sla_hours:
                p.sla_hours = spec.sla_hours
                p.save(update_fields=["sla_hours"])
            priorities[spec.name] = p

        # Perfil usuario: asignamos area y criticidad (pocos críticos)
        critical_requesters = set(rng.sample(requesters, k=max(2, int(len(requesters) * 0.08))))
        for r in requesters:
            area = rng.choice(areas)
            prof, _ = UserProfile.objects.get_or_create(user=r, defaults={"area": area, "rut": self._fake_rut(rng), "is_critical_actor": (r in critical_requesters)})
            # si existe, lo mantenemos coherente
            changed = False
            if getattr(prof, "area_id", None) != area.id:
                prof.area = area
                changed = True
            if getattr(prof, "is_critical_actor", False) != (r in critical_requesters):
                prof.is_critical_actor = (r in critical_requesters)
                changed = True
            if changed:
                prof.save()

        # AutoAsignación (reglas simples y coherentes)
        # - Para áreas críticas, preferimos técnicos específicos
        critical_areas = [a for a in areas if getattr(a, "is_critical", False)]
        noncritical_areas = [a for a in areas if a not in critical_areas]

        # Creamos reglas para que el sistema "tenga lógica"
        for cat in categories.values():
            for area in critical_areas:
                AutoAssignRule.objects.get_or_create(
                    category=cat,
                    area=area,
                    defaults={"tech": rng.choice(techs), "is_active": True, "created_at": rand_time_on_day(start, rng)},
                )
            for area in noncritical_areas[:2]:
                AutoAssignRule.objects.get_or_create(
                    category=cat,
                    area=area,
                    defaults={"tech": rng.choice(techs), "is_active": True, "created_at": rand_time_on_day(start, rng)},
                )

        # FAQs (con multimedia)
        for item in FAQS:
            FAQ.objects.get_or_create(
                question=item["question"],
                defaults={
                    "answer": item["answer"],
                    "created_at": rand_time_on_day(start, rng),
                    "updated_at": rand_time_on_day(start, rng),
                    "created_by": admin,
                    "updated_by": admin,
                    "category": None,
                    "subcategory": None,
                    "image": item.get("image") or "",
                    "video_file": item.get("video_file") or "",
                    "video_url": item.get("video_url") or "",
                },
            )

        # Generación de tickets con distribución anual
        total_tickets = int(opts["tickets"])
        created_dates = self._build_dates_distribution(start, end, total_tickets, rng)

        # Para asegurar “este mes” (diciembre) con resueltos y cerrados
        december_start = date(2025, 12, 1)
        december_dates = [d for d in created_dates if d >= december_start]
        if len(december_dates) < max(30, int(total_tickets * 0.08)):
            # si por azar quedaron pocos, forzamos algunos tickets a diciembre
            needed = max(30, int(total_tickets * 0.08)) - len(december_dates)
            for _ in range(needed):
                forced_day = date(2025, 12, rng.randint(1, 12))
                created_dates[rng.randrange(len(created_dates))] = forced_day

        rng.shuffle(created_dates)

        # Creamos tickets
        self.stdout.write(self.style.SUCCESS(f"Generando {total_tickets} tickets (2025-01-01 a 2025-12-12) ..."))
        breach_target_rate = rng.uniform(0.03, 0.06)  # 3% a 6%
        breach_budget = int(total_tickets * breach_target_rate)

        tickets_created = 0
        breaches_used = 0

        for i, day in enumerate(created_dates, start=1):
            created_at = rand_time_on_day(day, rng)

            # Clasificación realista
            kind = KIND_INCIDENT if rng.random() < 0.18 else KIND_REQUEST
            priority = self._pick_priority(priorities, kind, rng)
            requester = rng.choice(requesters)

            # Área: por perfil o aleatoria, pero coherente
            prof = UserProfile.objects.filter(user=requester).first()
            area = getattr(prof, "area", None) or rng.choice(areas)

            category = rng.choice(list(categories.values()))
            subcat_pool = Subcategory.objects.filter(category=category)
            subcategory = rng.choice(list(subcat_pool)) if subcat_pool.exists() and rng.random() < 0.85 else None

            # Asignación: algunos sin asignar para demo “autoasignación”
            assigned_to = None
            if day >= (end - timedelta(days=10)):
                # últimos días dejamos más sin asignar
                assigned_to = rng.choice(techs) if rng.random() < 0.55 else None
            else:
                assigned_to = rng.choice(techs) if rng.random() < 0.80 else None

            # Estado según antigüedad (evitamos tickets abiertos desde enero)
            days_old = (end - day).days
            status = self._pick_status(days_old, rng)

            # Duración hasta resolver/cerrar según SLA (con pocos vencidos)
            sla_hours = int(getattr(priority, "sla_hours", 24) or 24)
            due_at = created_at + timedelta(hours=sla_hours)

            resolved_at = None
            closed_at = None
            updated_at = created_at

            if status in {STATUS_RESOLVED, STATUS_CLOSED}:
                will_breach = (breaches_used < breach_budget) and (rng.random() < 0.5)
                if will_breach:
                    breaches_used += 1
                    # se vence “por poco” la mayoría
                    over = timedelta(hours=max(1, int(sla_hours * rng.uniform(0.10, 0.35))))
                    resolved_at = clamp_dt(due_at + over, end_dt)
                else:
                    # resuelve antes del SLA
                    under = timedelta(hours=max(1, int(sla_hours * rng.uniform(0.25, 0.85))))
                    resolved_at = clamp_dt(created_at + under, end_dt)

                updated_at = resolved_at

                if status == STATUS_CLOSED:
                    # cierra un poco después de resolver
                    close_delay = timedelta(hours=rng.randint(1, 48))
                    closed_at = clamp_dt(resolved_at + close_delay, end_dt)
                    updated_at = closed_at

            elif status == STATUS_IN_PROGRESS:
                # en progreso: actualizado recientemente
                move_delay = timedelta(hours=rng.randint(2, 72))
                updated_at = clamp_dt(created_at + move_delay, end_dt)

            else:
                # abierto: actualizado cercano
                move_delay = timedelta(hours=rng.randint(1, 24))
                updated_at = clamp_dt(created_at + move_delay, end_dt)

            # Code secuencial claro para demo
            code = f"TCK-2025-{i:05d}"

            ticket = Ticket.objects.create(
                code=code,
                title=self._make_title(kind, category, subcategory, rng),
                description=self._make_description(kind, rng),
                status=status,
                kind=kind,
                created_at=created_at,
                updated_at=updated_at,
                resolved_at=resolved_at,
                closed_at=closed_at,
                requester=requester,
                assigned_to=assigned_to,
                category=category,
                subcategory=subcategory,
                priority=priority,
                area=area,
                cluster_id=None if hasattr(Ticket, "cluster_id") else None,
            )

            tickets_created += 1

            # Comentarios / auditoría / eventos con horas distintas
            self._seed_ticket_activity(
                rng=rng,
                TicketComment=TicketComment,
                TicketAttachment=TicketAttachment,
                AuditLog=AuditLog,
                EventLog=EventLog,
                TicketAssignment=TicketAssignment,
                ticket=ticket,
                admin=admin,
                techs=techs,
                requester=requester,
                created_at=created_at,
                updated_at=updated_at,
                status=status,
                assigned_to=assigned_to,
                end_dt=end_dt,
            )

            # Notificaciones: área crítica o actor crítico -> técnicos + admin
            is_critical_area = bool(getattr(area, "is_critical", False))
            is_critical_actor = bool(getattr(prof, "is_critical_actor", False)) if prof else False

            if is_critical_area or is_critical_actor:
                when = clamp_dt(updated_at, end_dt)
                msg_flags = []
                if is_critical_area:
                    msg_flags.append("Área crítica")
                if is_critical_actor:
                    msg_flags.append("Usuario crítico")

                message = f"Ticket {ticket.code} marcado por {', '.join(msg_flags)}."
                url = f"/tickets/{ticket.id}/"

                # a admin
                Notification.objects.create(user=admin, message=message, url=url, is_read=False, created_at=when)
                # a técnicos
                for t in techs:
                    Notification.objects.create(user=t, message=message, url=url, is_read=False, created_at=when)

        # Aseguramos explícitamente que en diciembre hay RESOLVED y CLOSED
        dec_qs = Ticket.objects.filter(created_at__date__gte=december_start)
        dec_res = dec_qs.filter(status=STATUS_RESOLVED).count()
        dec_clo = dec_qs.filter(status=STATUS_CLOSED).count()
        if dec_res == 0 or dec_clo == 0:
            sample = list(dec_qs.order_by("-created_at")[:6])
            for idx, t in enumerate(sample):
                t.status = STATUS_CLOSED if idx % 2 == 0 else STATUS_RESOLVED
                if not t.resolved_at:
                    t.resolved_at = clamp_dt(t.created_at + timedelta(hours=2), end_dt)
                if t.status == STATUS_CLOSED and not t.closed_at:
                    t.closed_at = clamp_dt(t.resolved_at + timedelta(hours=6), end_dt)
                t.updated_at = t.closed_at or t.resolved_at or t.updated_at
                t.save()

        self.stdout.write(self.style.SUCCESS(f"OK. Tickets creados: {tickets_created}. SLA vencidos objetivo ~{int(breach_target_rate*100)}%."))

    # -----------------------------
    # Helpers internos
    # -----------------------------

    def _get_or_create_user(self, User, username: str, email: str, rng: random.Random, *, is_staff: bool, is_superuser: bool = False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
                "is_active": True,
            },
        )
        if created:
            user.set_password("Demo12345!")  # demo
            user.save()
        else:
            # mantener coherencia mínima
            changed = False
            if user.email != email:
                user.email = email
                changed = True
            if user.is_staff != is_staff:
                user.is_staff = is_staff
                changed = True
            if user.is_superuser != is_superuser:
                user.is_superuser = is_superuser
                changed = True
            if changed:
                user.save()
        return user

    def _fake_rut(self, rng: random.Random) -> str:
        base = rng.randint(10_000_000, 25_000_000)
        dv = rng.choice(list("0123456789K"))
        return f"{base}-{dv}"

    def _build_dates_distribution(self, start: date, end: date, n: int, rng: random.Random) -> list[date]:
        """
        Distribución anual realista:
        - Tickets repartidos por meses (con leve estacionalidad).
        - Garantiza presencia en todo el año.
        """
        # pesos por mes (enero a diciembre)
        weights = [0.95, 0.90, 1.05, 1.00, 0.95, 1.10, 1.00, 0.95, 1.10, 1.05, 1.00, 1.15]
        total_w = sum(weights)

        counts = [max(1, int(n * (w / total_w))) for w in weights]
        # ajustar para que sumen n
        while sum(counts) < n:
            counts[rng.randrange(12)] += 1
        while sum(counts) > n:
            idx = rng.randrange(12)
            if counts[idx] > 1:
                counts[idx] -= 1

        out: list[date] = []
        for month in range(1, 13):
            month_start = date(2025, month, 1)
            month_end = date(2025, month, 28)
            # ajuste real de fin de mes
            while True:
                try:
                    month_end = date(2025, month, month_end.day + 1)
                except ValueError:
                    break
            month_end = date(2025, month, month_end.day)

            # recorte por rango start-end
            lo = max(month_start, start)
            hi = min(month_end, end)
            if lo > hi:
                continue

            for _ in range(counts[month - 1]):
                delta_days = (hi - lo).days
                d = lo + timedelta(days=rng.randint(0, max(0, delta_days)))
                out.append(d)

        # si por recortes quedaron más/menos (raro), corregimos
        out = out[:n] if len(out) >= n else out + [end] * (n - len(out))
        return out

    def _pick_priority(self, priorities: dict, kind: str, rng: random.Random):
        # Incidentes tienden a ser más urgentes
        if kind == KIND_INCIDENT:
            r = rng.random()
            if r < 0.18:
                return priorities["Crítica"]
            if r < 0.45:
                return priorities["Alta"]
            if r < 0.85:
                return priorities["Media"]
            return priorities["Baja"]
        # Requests: más medias/bajas
        r = rng.random()
        if r < 0.05:
            return priorities["Crítica"]
        if r < 0.20:
            return priorities["Alta"]
        if r < 0.70:
            return priorities["Media"]
        return priorities["Baja"]

    def _pick_status(self, days_old: int, rng: random.Random) -> str:
        """
        Evita tickets abiertos desde enero:
        - Si es muy antiguo: casi todo cerrado/resuelto.
        - Si es reciente: mezcla de estados.
        """
        if days_old > 60:
            return STATUS_CLOSED if rng.random() < 0.70 else STATUS_RESOLVED
        if days_old > 30:
            r = rng.random()
            if r < 0.60:
                return STATUS_CLOSED
            if r < 0.90:
                return STATUS_RESOLVED
            return STATUS_IN_PROGRESS
        if days_old > 10:
            r = rng.random()
            if r < 0.45:
                return STATUS_CLOSED
            if r < 0.75:
                return STATUS_RESOLVED
            if r < 0.92:
                return STATUS_IN_PROGRESS
            return STATUS_OPEN
        # muy reciente: más abiertos/en progreso para que el técnico tenga “cola”
        r = rng.random()
        if r < 0.25:
            return STATUS_OPEN
        if r < 0.60:
            return STATUS_IN_PROGRESS
        if r < 0.85:
            return STATUS_RESOLVED
        return STATUS_CLOSED

    def _make_title(self, kind: str, category, subcategory, rng: random.Random) -> str:
        base = "Incidente" if kind == KIND_INCIDENT else "Solicitud"
        cat = getattr(category, "name", "General")
        sub = getattr(subcategory, "name", "")
        suffix = f" - {sub}" if sub else ""
        return f"{base}: {cat}{suffix}"

    def _make_description(self, kind: str, rng: random.Random) -> str:
        if kind == KIND_INCIDENT:
            samples = [
                "El servicio presenta intermitencia. Se requiere revisión prioritaria.",
                "Usuarios reportan lentitud general. Impacta continuidad operativa.",
                "Hay un error crítico al intentar acceder. Se adjuntará evidencia si aplica.",
            ]
        else:
            samples = [
                "Necesito apoyo para habilitar acceso o resolver una configuración.",
                "Solicito asistencia para instalar o actualizar una herramienta de trabajo.",
                "Requiero orientación para completar el procedimiento correctamente.",
            ]
        return rng.choice(samples)

    def _seed_ticket_activity(
        self,
        *,
        rng: random.Random,
        TicketComment,
        TicketAttachment,
        AuditLog,
        EventLog,
        TicketAssignment,
        ticket,
        admin,
        techs,
        requester,
        created_at: datetime,
        updated_at: datetime,
        status: str,
        assigned_to,
        end_dt: datetime,
    ):
        # Acción: creación
        AuditLog.objects.create(
            ticket=ticket,
            actor=requester,
            action="CREATE",
            meta={"status": status, "kind": getattr(ticket, "kind", "")},
            created_at=created_at + timedelta(minutes=rng.randint(1, 25)),
        )
        EventLog.objects.create(
            model="tickets.ticket",
            obj_id=ticket.id,
            action="CREATE",
            message=f"Creación de ticket {ticket.code}",
            resource_id=ticket.id,
            actor=requester,
            created_at=created_at + timedelta(minutes=rng.randint(2, 40)),
        )

        # Comentario inicial (a veces)
        if rng.random() < 0.55:
            t = clamp_dt(created_at + timedelta(hours=rng.randint(1, 8)), end_dt)
            TicketComment.objects.create(
                ticket=ticket,
                author=requester,
                body="Aporto más detalle del caso para facilitar el diagnóstico.",
                is_internal=False,
                created_at=t,
            )
            AuditLog.objects.create(
                ticket=ticket,
                actor=requester,
                action="COMMENT",
                meta={"scope": "public"},
                created_at=clamp_dt(t + timedelta(minutes=rng.randint(1, 20)), end_dt),
            )

        # Asignación (si tiene assigned_to)
        if assigned_to:
            t = clamp_dt(created_at + timedelta(hours=rng.randint(2, 24)), end_dt)
            AuditLog.objects.create(
                ticket=ticket,
                actor=admin if rng.random() < 0.35 else assigned_to,
                action="ASSIGN",
                meta={"to": getattr(assigned_to, "username", "")},
                created_at=t,
            )
            EventLog.objects.create(
                model="tickets.ticket",
                obj_id=ticket.id,
                action="ASSIGN",
                message=f"Asignado a {getattr(assigned_to, 'username', '')}",
                resource_id=ticket.id,
                actor=admin if rng.random() < 0.35 else assigned_to,
                created_at=clamp_dt(t + timedelta(minutes=rng.randint(1, 35)), end_dt),
            )
            if TicketAssignment and rng.random() < 0.35:
                TicketAssignment.objects.create(
                    ticket=ticket,
                    from_user=None,
                    to_user=assigned_to,
                    reason="Asignación inicial",
                    created_at=t,
                )

        # Adjuntos (algunas veces)
        if rng.random() < 0.25:
            t = clamp_dt(created_at + timedelta(hours=rng.randint(4, 72)), end_dt)
            TicketAttachment.objects.create(
                ticket=ticket,
                uploaded_by=requester,
                file="evidencia.png",
                content_type="image/png",
                size=rng.randint(50_000, 900_000),
                uploaded_at=t,
            )
            AuditLog.objects.create(
                ticket=ticket,
                actor=requester,
                action="ATTACH",
                meta={"file": "evidencia.png"},
                created_at=clamp_dt(t + timedelta(minutes=rng.randint(1, 20)), end_dt),
            )

        # Cambios de estado (si no quedó OPEN)
        if status in {STATUS_IN_PROGRESS, STATUS_RESOLVED, STATUS_CLOSED}:
            # paso a IN_PROGRESS en muchos casos
            if status != STATUS_OPEN and rng.random() < 0.70:
                t = clamp_dt(created_at + timedelta(hours=rng.randint(6, 96)), end_dt)
                AuditLog.objects.create(
                    ticket=ticket,
                    actor=assigned_to or rng.choice(techs),
                    action="STATUS",
                    meta={"from": STATUS_OPEN, "to": STATUS_IN_PROGRESS},
                    created_at=t,
                )
                EventLog.objects.create(
                    model="tickets.ticket",
                    obj_id=ticket.id,
                    action="STATUS",
                    message="Estado cambiado a En progreso",
                    resource_id=ticket.id,
                    actor=assigned_to or rng.choice(techs),
                    created_at=clamp_dt(t + timedelta(minutes=rng.randint(1, 20)), end_dt),
                )
                # comentario interno técnico ocasional
                if rng.random() < 0.35:
                    TicketComment.objects.create(
                        ticket=ticket,
                        author=assigned_to or rng.choice(techs),
                        body="Nota interna: se inició diagnóstico y se revisan posibles causas.",
                        is_internal=True,
                        created_at=clamp_dt(t + timedelta(minutes=rng.randint(10, 90)), end_dt),
                    )

        # Cierre / resolución (si aplica)
        if status in {STATUS_RESOLVED, STATUS_CLOSED}:
            t = clamp_dt(updated_at - timedelta(hours=rng.randint(1, 6)), end_dt)
            AuditLog.objects.create(
                ticket=ticket,
                actor=assigned_to or rng.choice(techs),
                action="STATUS",
                meta={"to": status},
                created_at=t,
            )
            EventLog.objects.create(
                model="tickets.ticket",
                obj_id=ticket.id,
                action="STATUS",
                message=f"Estado cambiado a {status}",
                resource_id=ticket.id,
                actor=assigned_to or rng.choice(techs),
                created_at=clamp_dt(t + timedelta(minutes=rng.randint(1, 20)), end_dt),
            )
