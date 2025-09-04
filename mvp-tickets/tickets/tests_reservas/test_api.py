from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model


class ReservaApiTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.staff = self.User.objects.create_user(
            username='admin', password='x', is_staff=True
        )
        self.user = self.User.objects.create_user(username='u', password='x')

    def crear_policy_resource(self, policy_data=None, resource_data=None):
        self.client.login(username='admin', password='x')
        policy_payload = {
            'name': 'Default',
            'max_hours': 4,
            'min_notice_hours': 0,
            'allow_weekends': True,
            'buffer_minutes': 0,
        }
        if policy_data:
            policy_payload.update(policy_data)
        resp_pol = self.client.post(
            reverse('booking-policy-list'),
            data=policy_payload,
            content_type='application/json'
        )
        self.assertIn(resp_pol.status_code, (200, 201))
        resource_payload = {
            'name': 'Sala 1',
            'type': 'room',
            'capacity': 1,
        }
        if resource_data:
            resource_payload.update(resource_data)
        resp_res = self.client.post(
            reverse('booking-resource-list'),
            data=resource_payload,
            content_type='application/json'
        )
        self.assertIn(resp_res.status_code, (200, 201))
        self.client.logout()
        return resp_res.json()['id']

    def test_staff_crea_policy_y_resource(self):
        self.crear_policy_resource()

    def test_crear_reserva_y_disponibilidad(self):
        resource_id = self.crear_policy_resource()
        self.client.login(username='u', password='x')
        url = reverse('booking-reservation-list')
        start = timezone.now() + timedelta(hours=1)
        end = start + timedelta(hours=1)
        payload = {
            'resource': resource_id,
            'starts_at': start.isoformat(),
            'ends_at': end.isoformat(),
        }
        resp = self.client.post(url, data=payload, content_type='application/json')
        self.assertIn(resp.status_code, (200, 201))
        res_id = resp.json()['id']
        avail = self.client.get(
            reverse('booking-reservation-availability'),
            {'resource_id': resource_id, 'from': start.isoformat(), 'to': end.isoformat()}
        )
        self.assertEqual(avail.status_code, 200)
        ids = [r['id'] for r in avail.json()]
        self.assertIn(res_id, ids)

    def test_solapamiento_conflict(self):
        resource_id = self.crear_policy_resource()
        self.client.login(username='u', password='x')
        url = reverse('booking-reservation-list')
        start = timezone.now() + timedelta(hours=1)
        end = start + timedelta(hours=1)
        payload = {
            'resource': resource_id,
            'starts_at': start.isoformat(),
            'ends_at': end.isoformat(),
        }
        self.client.post(url, data=payload, content_type='application/json')
        payload2 = {
            'resource': resource_id,
            'starts_at': (start + timedelta(minutes=30)).isoformat(),
            'ends_at': (end + timedelta(minutes=30)).isoformat(),
        }
        resp2 = self.client.post(url, data=payload2, content_type='application/json')
        self.assertEqual(resp2.status_code, 409)

    def test_politica_max_horas(self):
        resource_id = self.crear_policy_resource({'max_hours': 1})
        self.client.login(username='u', password='x')
        url = reverse('booking-reservation-list')
        start = timezone.now() + timedelta(hours=1)
        end = start + timedelta(hours=2)
        resp = self.client.post(
            url,
            data={
                'resource': resource_id,
                'starts_at': start.isoformat(),
                'ends_at': end.isoformat(),
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
