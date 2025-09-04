from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from tickets.models_reservas import Resource, Policy


class ReservaApiTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username='u', password='x')
        self.client.login(username='u', password='x')
        self.resource = Resource.objects.create(name='Sala 1', type='room')
        Policy.objects.create(name='Default', max_hours=4, min_notice_hours=0, allow_weekends=True, buffer_minutes=0)

    def test_crear_reserva_ok(self):
        url = reverse('booking-reservation-list')
        payload = {
            'resource': self.resource.id,
            'starts_at': (timezone.now() + timedelta(hours=1)).isoformat(),
            'ends_at': (timezone.now() + timedelta(hours=2)).isoformat(),
        }
        resp = self.client.post(url, data=payload, content_type='application/json')
        self.assertIn(resp.status_code, (200, 201))
