from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from catalog.models import Category, Priority, Area
from tickets.forms import FAQForm
from tickets.models import Notification, Ticket
from tickets.services_critical import annotate_critical_score, notify_if_critical

User = get_user_model()


class CriticalFlowTests(TestCase):
    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="ADMINISTRADOR")
        self.tech_group, _ = Group.objects.get_or_create(name="TECNICO")
        self.admin = User.objects.create_user(username="admin", password="pass")
        self.admin.groups.add(self.admin_group)
        self.tech = User.objects.create_user(username="tech", password="pass")
        self.tech.groups.add(self.tech_group)
        self.actor = User.objects.create_user(username="manager", password="pass")
        self.actor.profile.is_critical_actor = True
        self.actor.profile.save(update_fields=["is_critical_actor"])

        self.category = Category.objects.create(name="Cat")
        self.priority = Priority.objects.create(name="Alta", sla_hours=48)
        self.area = Area.objects.create(name="Operaciones", is_critical=True)

    def test_notify_if_critical_targets_roles(self):
        ticket = Ticket.objects.create(
            title="Critico",
            description="",
            requester=self.admin,
            category=self.category,
            priority=self.priority,
            area=self.area,
        )

        notify_if_critical(ticket, self.actor, "realizó una acción")

        recipients = set(Notification.objects.values_list("user__username", flat=True))
        self.assertIn(self.admin.username, recipients)
        self.assertIn(self.tech.username, recipients)

    def test_annotation_orders_by_score(self):
        base_ticket = Ticket.objects.create(
            title="Normal",
            description="",
            requester=self.admin,
            category=self.category,
            priority=self.priority,
        )
        critical_ticket = Ticket.objects.create(
            title="Critico area",
            description="",
            requester=self.admin,
            category=self.category,
            priority=self.priority,
            area=self.area,
        )

        annotated = annotate_critical_score(Ticket.objects.all(), actor=self.actor).order_by(
            "-critical_score", "-priority__sla_hours", "created_at"
        )
        ordered = list(annotated)
        self.assertEqual(ordered[0], critical_ticket)
        self.assertEqual(ordered[1], base_ticket)

    def test_faq_form_accepts_media(self):
        buffer = BytesIO()
        image_file = Image.new("RGB", (1, 1), "red")
        image_file.save(buffer, format="PNG")
        image = SimpleUploadedFile("faq.png", buffer.getvalue(), content_type="image/png")
        video = SimpleUploadedFile("demo.mp4", b"\x00\x00\x00\x14ftypmp42", content_type="video/mp4")
        form = FAQForm(
            data={
                "question": "Pregunta",
                "answer": "respuesta",
            },
            files={
                "image": image,
                "video_file": video,
                "video_url": "https://example.com/video",
            },
        )
        self.assertTrue(form.is_valid())
