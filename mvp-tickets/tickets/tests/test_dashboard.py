import json
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Priority, Subcategory
from tickets.models import Ticket


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
