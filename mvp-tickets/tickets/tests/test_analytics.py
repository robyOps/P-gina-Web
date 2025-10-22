import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
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

    def test_build_ticket_heatmap_counts_by_hour(self):
        now = timezone.now()
        t1 = self._create_ticket(title="Ingreso lento")
        t2 = self._create_ticket(title="Error 500")

        Ticket.objects.filter(pk=t1.pk).update(created_at=now - timedelta(hours=1))
        Ticket.objects.filter(pk=t2.pk).update(created_at=now - timedelta(hours=5))

        payload = build_ticket_heatmap(Ticket.objects.all(), since=now - timedelta(days=1))

        self.assertEqual(payload.overall_total, 2)
        flattened = [count for row in payload.matrix for count in row]
        self.assertIn(1, flattened)

    def test_build_ticket_heatmap_uses_local_timezone(self):
        tz = timezone.get_current_timezone()
        aware = timezone.datetime(2024, 7, 1, 15, 30, tzinfo=tz)
        ticket = self._create_ticket(title="Falla horario")

        Ticket.objects.filter(pk=ticket.pk).update(created_at=aware)

        payload = build_ticket_heatmap(
            Ticket.objects.all(), since=aware - timedelta(days=1)
        )

        self.assertEqual(payload.overall_total, 1)
        self.assertEqual(payload.matrix[0][15], 1)

    def test_recent_ticket_alerts_detects_warning_and_breach(self):
        now = timezone.now()
        overdue = self._create_ticket(title="Portal caído", assigned_to=self.tech)
        warning = self._create_ticket(title="Reinicio programado")

        Ticket.objects.filter(pk=overdue.pk).update(created_at=now - timedelta(hours=36))
        Ticket.objects.filter(pk=warning.pk).update(created_at=now - timedelta(hours=20))

        data = recent_ticket_alerts(Ticket.objects.all(), warn_ratio=0.75, limit=5)

        self.assertGreaterEqual(data["summary"]["breaches"], 1)
        self.assertGreaterEqual(data["summary"]["warnings"], 1)
        self.assertTrue(data["items"])

    def test_aggregate_top_subcategories_respects_limit(self):
        self._create_ticket(subcategory=self.subcategory)
        self._create_ticket(subcategory=self.subcategory)
        self._create_ticket(subcategory=self.alt_subcategory)

        results = aggregate_top_subcategories(Ticket.objects.all(), limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subcategory"], self.subcategory.name)


class DashboardAnalyticsPerformanceTests(TestCase):
    """Smoke tests that validate the performance of analytics helpers."""

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
        self.alt_subcategory = Subcategory.objects.create(
            category=self.category, name="Accesos"
        )

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

    def test_build_ticket_heatmap_is_generated_under_one_second(self):
        now = timezone.now()
        tickets = []
        for hour in range(24):
            for index in range(5):
                ticket = self._create_ticket(title=f"Ticket {hour}-{index}")
                Ticket.objects.filter(pk=ticket.pk).update(
                    created_at=now - timedelta(hours=hour)
                )
                tickets.append(ticket.pk)

        start = time.perf_counter()
        payload = build_ticket_heatmap(
            Ticket.objects.filter(pk__in=tickets), since=now - timedelta(days=7)
        )
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0, f"Heatmap tardó {elapsed:.3f}s en generarse")
        self.assertEqual(payload.overall_total, len(tickets))

    def test_aggregate_top_subcategories_completes_quickly(self):
        for _ in range(60):
            self._create_ticket(subcategory=self.subcategory)
            self._create_ticket(subcategory=self.alt_subcategory)

        start = time.perf_counter()
        results = aggregate_top_subcategories(Ticket.objects.all(), limit=5)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.75, f"Agregación tardó {elapsed:.3f}s")
        self.assertEqual(sum(row["total"] for row in results), 120)
