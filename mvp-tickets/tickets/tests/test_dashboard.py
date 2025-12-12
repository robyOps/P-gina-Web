import json
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Priority, Subcategory
from tickets.models import AuditLog, Ticket, TicketAssignment
from tickets.views import _average_resolution_hours


class DashboardHistoricalRangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pass1234"
        )
        self.client.force_login(self.user)

        self.category = Category.objects.create(name="Infraestructura")
        self.subcategory = Subcategory.objects.create(
            category=self.category, name="Red"
        )
        self.priority = Priority.objects.create(name="Alta", sla_hours=24)

    def _create_ticket(self, created_at):
        ticket = Ticket.objects.create(
            title="Falla histórica",
            description="Ticket con fecha antigua",
            requester=self.user,
            category=self.category,
            subcategory=self.subcategory,
            priority=self.priority,
            status=Ticket.OPEN,
        )
        Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at)
        return Ticket.objects.get(pk=ticket.pk)

    @mock.patch("tickets.views.timezone.now")
    def test_historical_mode_extends_period_until_now(self, mock_now):
        tz = timezone.get_current_timezone()
        fixed_now = timezone.make_aware(datetime(2024, 11, 4, 15, 30), tz)
        mock_now.return_value = fixed_now

        history_start = fixed_now - timedelta(days=90)
        self._create_ticket(history_start)

        response = self.client.get(reverse("dashboard"), {"mode": "historical"})

        self.assertEqual(response.status_code, 200)
        period = response.context["period_range"]
        expected_start = history_start.astimezone(period["start"].tzinfo)
        expected_end = fixed_now.astimezone(period["end"].tzinfo)
        self.assertEqual(period["start"], expected_start)
        self.assertEqual(period["end"], expected_end)

        payload = json.loads(response.context["period_payload"])
        self.assertEqual(payload["start"], period["start"].isoformat())
        self.assertEqual(payload["end"], period["end"].isoformat())


class DashboardAssignmentsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pass1234"
        )
        self.client.force_login(self.user)

        self.category = Category.objects.create(name="Infraestructura")
        self.subcategory = Subcategory.objects.create(
            category=self.category, name="Red"
        )
        self.priority = Priority.objects.create(name="Alta", sla_hours=24)
        self.ticket = Ticket.objects.create(
            title="Asignación diaria",
            description="",
            requester=self.user,
            category=self.category,
            subcategory=self.subcategory,
            priority=self.priority,
            status=Ticket.OPEN,
        )

    def test_dashboard_counts_assignments_today_only(self):
        yesterday = timezone.now() - timedelta(days=1)
        TicketAssignment.objects.create(
            ticket=self.ticket, from_user=self.user, to_user=self.user, reason="ayer"
        )
        TicketAssignment.objects.filter(reason="ayer").update(created_at=yesterday)

        TicketAssignment.objects.create(
            ticket=self.ticket, from_user=self.user, to_user=self.user, reason="hoy"
        )

        response = self.client.get(reverse("dashboard"))
        breakdown = json.loads(response.context["assignments_today_breakdown"])

        self.assertEqual(response.context["assignments_today"], 1)
        self.assertEqual(breakdown["total"], 1)
        self.assertEqual(breakdown["assigned"], 0)
        self.assertEqual(breakdown["auto_assigned"], 1)
        self.assertEqual(breakdown["reassigned"], 0)

    def test_dashboard_falls_back_to_auditlog_assignments(self):
        AuditLog.objects.create(ticket=self.ticket, actor=self.user, action="ASSIGN", meta={"reason": "auto-assign"})

        response = self.client.get(reverse("dashboard"))
        breakdown = json.loads(response.context["assignments_today_breakdown"])

        self.assertEqual(response.context["assignments_today"], 1)
        self.assertEqual(breakdown["auto_assigned"], 1)
        self.assertEqual(breakdown["reassigned"], 0)


class AverageResolutionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pass1234"
        )
        self.category = Category.objects.create(name="Infraestructura")
        self.subcategory = Subcategory.objects.create(
            category=self.category, name="Red"
        )
        self.priority = Priority.objects.create(name="Alta", sla_hours=24)

    def _create_ticket(self, created_at, done_at=None):
        ticket = Ticket.objects.create(
            title="TPR",
            description="",
            requester=self.user,
            category=self.category,
            subcategory=self.subcategory,
            priority=self.priority,
            status=Ticket.OPEN,
        )
        Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at, resolved_at=done_at)
        return Ticket.objects.get(pk=ticket.pk)

    def test_average_resolution_ignores_negative_durations(self):
        now = timezone.now()
        self._create_ticket(created_at=now, done_at=now - timedelta(hours=2))
        valid = self._create_ticket(created_at=now - timedelta(hours=5), done_at=now)

        avg_hours = _average_resolution_hours(Ticket.objects.all())

        expected_hours = round((valid.resolved_at - valid.created_at).total_seconds() / 3600, 2)
        self.assertEqual(avg_hours, expected_hours)
        self.assertGreaterEqual(avg_hours, 0)
