import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ChatSessionViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chat-user", email="chat@example.com", password="pass1234"
        )
        self.client.force_login(self.user)

    def test_chat_session_renders_json_script_payload(self):
        session = self.client.session
        session["chat_history"] = [
            {"author": "user", "message": "Hola"},
            {"author": "assistant", "message": "Bienvenido"},
        ]
        session.save()

        response = self.client.get(reverse("chat_session"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("chat/session.html", [template.name for template in response.templates])
        self.assertContains(response, 'type="application/json"', status_code=200)

        html = response.content.decode("utf-8")
        match = re.search(
            r'<script[^>]*id="chat-initial-data"[^>]*>(?P<payload>.*?)</script>',
            html,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "No se encontró el bloque JSON incrustado")

        payload = match.group("payload").strip()
        self.assertJSONEqual(payload, json.dumps(session["chat_history"]))
