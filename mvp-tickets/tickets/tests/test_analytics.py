import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.utils import timezone

from catalog.models import Category, Priority, Subcategory

from tickets.models import Ticket
from tickets.utils import (
    aggregate_top_subcategories,
    build_ticket_heatmap,
    recent_ticket_alerts,
)


class DashboardAnalyticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="requester", email="req@example.com", password="pass1234"
        )
        self.tech = get_user_model().objects.create_user(
            username="tech", email="tech@example.com", password="pass1234"
        )
        self.category = Category.objects.create(name="Soporte")
        self.priority = Priority.objects.create(name="Alta", sla_hours=24)
        self.subcategory = Subcategory.objects.create(category=self.category, name="VPN")
        self.alt_subcategory = Subcategory.objects.create(category=self.category, name="Accesos")

    def _create_ticket(self, **kwargs) -> Ticket:
        defaults = {
            "title": "Falla VPN",
            "description": "La conexión VPN no responde",
            "requester": self.user,
            "category": self.category,
            "subcategory": self.subcategory,
            "priority": self.priority,
            "status": Ticket.OPEN,
        }
        defaults.update(kwargs)
        return Ticket.objects.create(**defaults)

    @tag("unitaria")
    def test_build_ticket_heatmap_counts_by_hour(self):
        """Cuenta los tickets por cada hora del último día y verifica que el total sea correcto."""
        now = timezone.now()
        t1 = self._create_ticket(title="Ingreso lento")
        t2 = self._create_ticket(title="Error 500")

        Ticket.objects.filter(pk=t1.pk).update(created_at=now - timedelta(hours=1))
        Ticket.objects.filter(pk=t2.pk).update(created_at=now - timedelta(hours=5))

        payload = build_ticket_heatmap(Ticket.objects.all(), since=now - timedelta(days=1))

        self.assertEqual(payload.overall_total, 2)
        flattened = [count for row in payload.matrix for count in row]
        self.assertIn(1, flattened)

    @tag("unitaria")
    def test_build_ticket_heatmap_uses_local_timezone(self):
        """Coloca cada conteo en la hora correcta según la zona horaria local."""
        tz = timezone.get_current_timezone()
        aware = timezone.datetime(2024, 7, 1, 15, 30, tzinfo=tz)
        ticket = self._create_ticket(title="Falla horario")

        Ticket.objects.filter(pk=ticket.pk).update(created_at=aware)

        payload = build_ticket_heatmap(
            Ticket.objects.all(), since=aware - timedelta(days=1)
        )

        self.assertEqual(payload.overall_total, 1)
        self.assertEqual(payload.matrix[0][15], 1)

    @tag("unitaria")
    def test_recent_ticket_alerts_detects_warning_and_breach(self):
        """Detecta avisos e incumplimientos del SLA comparando horas transcurridas."""
        now = timezone.now()
        overdue = self._create_ticket(title="Portal caído", assigned_to=self.tech)
        warning = self._create_ticket(title="Reinicio programado")

        Ticket.objects.filter(pk=overdue.pk).update(created_at=now - timedelta(hours=36))
        Ticket.objects.filter(pk=warning.pk).update(created_at=now - timedelta(hours=20))

        data = recent_ticket_alerts(Ticket.objects.all(), warn_ratio=0.75, limit=5)

        self.assertGreaterEqual(data["summary"]["breaches"], 1)
        self.assertGreaterEqual(data["summary"]["warnings"], 1)
        self.assertTrue(data["items"])

    @tag("unitaria")
    def test_aggregate_top_subcategories_respects_limit(self):
        """Devuelve solo las subcategorías más frecuentes respetando el límite recibido."""
        self._create_ticket(subcategory=self.subcategory)
        self._create_ticket(subcategory=self.subcategory)
        self._create_ticket(subcategory=self.alt_subcategory)

        results = aggregate_top_subcategories(Ticket.objects.all(), limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subcategory"], self.subcategory.name)


class DashboardAnalyticsPerformanceTests(TestCase):
    def setUp(self):
        self.requester = get_user_model().objects.create_user(
            username="perf", email="perf@example.com", password="pass1234"
        )
        self.category = Category.objects.create(name="SOPORTE")
        self.subcategory = Subcategory.objects.create(category=self.category, name="VPN")
        self.priority = Priority.objects.create(name="Normal", sla_hours=24)
        now = timezone.now()
        # Carga de ejemplo
        for i in range(300):
            Ticket.objects.create(
                title=f"T{i}", description="x",
                requester=self.requester,
                category=self.category, subcategory=self.subcategory,
                priority=self.priority, created_at=now
            )

    @tag("rendimiento")
    def test_aggregate_top_subcategories_completes_quickly(self):
        """Calcula el “Top de subcategorías” con datos de ejemplo en ≤ 1 segundo."""
        t0 = time.perf_counter()
        _ = list(aggregate_top_subcategories(Ticket.objects.all(), limit=5))
        dt = time.perf_counter() - t0
        self.assertLessEqual(dt, 1.0)

    @tag("rendimiento")
    def test_build_ticket_heatmap_is_generated_under_one_second(self):
        """Genera el mapa de calor de tickets en ≤ 1 segundo."""
        since = timezone.now() - timezone.timedelta(days=1)
        t0 = time.perf_counter()
        _ = build_ticket_heatmap(Ticket.objects.all(), since=since)
        dt = time.perf_counter() - t0
        self.assertLessEqual(dt, 1.0)


DashboardAnalyticsTests.test_build_ticket_heatmap_counts_by_hour.__django_test_tags__ = {"unitaria"}
DashboardAnalyticsTests.test_build_ticket_heatmap_uses_local_timezone.__django_test_tags__ = {"unitaria"}
DashboardAnalyticsTests.test_recent_ticket_alerts_detects_warning_and_breach.__django_test_tags__ = {"unitaria"}
DashboardAnalyticsTests.test_aggregate_top_subcategories_respects_limit.__django_test_tags__ = {"unitaria"}
DashboardAnalyticsPerformanceTests.test_aggregate_top_subcategories_completes_quickly.__django_test_tags__ = {"rendimiento"}
DashboardAnalyticsPerformanceTests.test_build_ticket_heatmap_is_generated_under_one_second.__django_test_tags__ = {"rendimiento"}
