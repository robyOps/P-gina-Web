from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Priority
from tickets.models import Ticket


class ReportsExportExcelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pass")
        cat = Category.objects.create(name="Cat")
        pri = Priority.objects.create(key=Priority.LOW)
        Ticket.objects.create(
            code="T1",
            title="Test",
            description="d",
            requester=self.user,
            category=cat,
            priority=pri,
        )

    def test_export_excel(self):
        self.client.login(username="u1", password="pass")
        url = reverse("reports_export_excel")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        from openpyxl import load_workbook

        wb = load_workbook(filename=BytesIO(resp.content))
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        self.assertIn("code", headers)
        first_row = [cell.value for cell in next(ws.iter_rows(min_row=2, max_row=2))]
        self.assertEqual(first_row[0], "T1")

