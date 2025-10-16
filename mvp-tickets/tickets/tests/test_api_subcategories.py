from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from catalog.models import Area, Category, Priority, Subcategory
from tickets.backfill import SubcategoryBackfillReport
from tickets.models import Ticket


class TicketApiBase(APITestCase):
    def setUp(self) -> None:  # noqa: D401 - inherited docstring not required
        super().setUp()
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            password="pass1234",
            is_superuser=True,
        )
        self.client.force_authenticate(self.admin)
        self.priority = Priority.objects.create(name="Alta", sla_hours=24)
        self.category = Category.objects.create(name="Soporte")
        self.subcategory = Subcategory.objects.create(category=self.category, name="VPN")
        self.area = Area.objects.create(name="Operaciones")

    def _create_ticket(self, **overrides) -> Ticket:
        payload = {
            "title": "Falla VPN",
            "description": "No conecta",
            "requester": self.admin,
            "category": self.category,
            "subcategory": self.subcategory,
            "priority": self.priority,
            "area": self.area,
            "status": Ticket.OPEN,
        }
        payload.update(overrides)
        ticket = Ticket.objects.create(**payload)
        created_at = overrides.get("created_at")
        if created_at is not None:
            Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at)
            ticket.refresh_from_db()
        return ticket


class TicketFilterOptionsApiTests(TicketApiBase):
    def test_returns_active_catalog_entries(self):
        inactive_category = Category.objects.create(name="Deprecated", is_active=False)
        Subcategory.objects.create(category=self.category, name="Accesos", is_active=False)
        Subcategory.objects.create(category=inactive_category, name="Legacy VPN")
        other_area = Area.objects.create(name="Infraestructura")

        response = self.client.get(reverse("tickets_filters"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("categorias", data)
        self.assertIn("subcategorias", data)
        self.assertIn("areas", data)

        category_names = {entry["name"] for entry in data["categorias"]}
        self.assertIn("SOPORTE", category_names)
        self.assertNotIn("DEPRECATED", category_names)

        sub_map = data["subcategorias"].get(str(self.category.id), [])
        sub_names = {entry["name"] for entry in sub_map}
        self.assertIn("VPN", sub_names)
        self.assertNotIn("Accesos", sub_names)

        area_names = {entry["name"] for entry in data["areas"]}
        self.assertEqual(area_names, {self.area.name, other_area.name})


class SubcategoryBackfillApiTests(TicketApiBase):
    def setUp(self) -> None:  # noqa: D401
        super().setUp()
        self.url = reverse("tickets_backfill_subcategories")

    def test_requires_privileged_user(self):
        user = get_user_model().objects.create_user(
            username="plain",
            email="plain@example.com",
            password="pass1234",
        )
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("tickets.api.run_subcategory_backfill")
    def test_returns_backfill_report_payload(self, mock_run):
        mock_run.return_value = SubcategoryBackfillReport(
            total=5,
            completed=4,
            pending=1,
            deterministic_matches=2,
            heuristic_matches=1,
        )

        response = self.client.post(self.url, {"dry_run": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["total"], 5)
        self.assertEqual(payload["completados"], 4)
        self.assertEqual(payload["pendientes"], 1)
        self.assertAlmostEqual(payload["cobertura_pct"], 80.0)
        self.assertTrue(payload["dry_run"])
        mock_run.assert_called_once_with(dry_run=True)


class TicketReportsApiTests(TicketApiBase):
    def setUp(self) -> None:  # noqa: D401
        super().setUp()
        self.other_area = Area.objects.create(name="Desarrollo")
        self.other_subcategory = Subcategory.objects.create(
            category=self.category,
            name="Correo",
        )

    def test_endpoints_require_authentication(self):
        url = reverse("reports_top_subcategories")
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_top_subcategories_endpoint(self):
        self._create_ticket()
        self._create_ticket()
        self._create_ticket(subcategory=self.other_subcategory)

        url = reverse("reports_top_subcategories")
        response = self.client.get(url, {"limit": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        results = data["results"]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["subcategory"], "VPN")
        self.assertEqual(results[0]["total"], 2)
        self.assertAlmostEqual(results[0]["percentage"], 66.67, places=2)
        self.assertEqual(results[0]["category"], "SOPORTE")

    def test_area_by_subcategory_endpoint(self):
        self._create_ticket()
        self._create_ticket(area=self.other_area, subcategory=self.other_subcategory)
        self._create_ticket(area=self.area, subcategory=self.other_subcategory)
        self._create_ticket(area=self.area, subcategory=self.other_subcategory)

        url = reverse("reports_area_by_subcategory")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        rows = response.json()["results"]
        self.assertTrue(rows)
        top_row = rows[0]
        self.assertEqual(top_row["area"], self.area.name)
        self.assertEqual(top_row["subcategory"], "Correo")
        self.assertEqual(top_row["total"], 2)

    def test_area_subcategory_heatmap_endpoint(self):
        now = timezone.now()
        old = now - timedelta(days=45)
        self._create_ticket(created_at=now)
        self._create_ticket(area=self.area, subcategory=self.other_subcategory, created_at=now)
        self._create_ticket(area=self.other_area, subcategory=self.other_subcategory, created_at=old)

        url = reverse("reports_area_subcat_heatmap")
        response = self.client.get(url, {"from": now.date().isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(sorted(data["areas"]), sorted({self.area.name}))
        self.assertIn("matrix", data)
        self.assertIn("cells", data)
        cells = {(cell["area"], cell["subcategory"]): cell["count"] for cell in data["cells"]}
        self.assertEqual(cells[(self.area.name, "Correo")], 1)
        self.assertEqual(cells[(self.area.name, "VPN")], 1)
