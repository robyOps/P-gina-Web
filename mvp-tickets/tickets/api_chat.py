"""Endpoint del chatbot interno con permisos por rol."""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from .services_chat import (
    build_chat_context,
    call_ai_api,
    determine_user_role,
    is_prompt_injection_attempt,
)


logger = logging.getLogger(__name__)


class ChatView(APIView):
    """Gestiona la conversación con el asistente de IA usando sesión de usuario."""

    permission_classes = [IsAuthenticated]
    session_key = "chat_history"
    max_history = 40

    def _load_history(self, request):
        history = request.session.get(self.session_key, [])
        cleaned: list[dict[str, str]] = []
        if isinstance(history, list):
            for entry in history:
                if not isinstance(entry, dict):
                    continue
                author = entry.get("author")
                message = entry.get("message")
                if author in {"user", "assistant"} and isinstance(message, str):
                    cleaned.append({"author": author, "message": message})
        if cleaned != history:
            request.session[self.session_key] = cleaned
            request.session.modified = True
        return cleaned

    def get(self, request):
        """Devuelve la conversación actual almacenada en la sesión."""

        return Response({"conversation": self._load_history(request)})

    def delete(self, request):
        """Elimina la conversación persistida en la sesión del usuario."""

        if self.session_key in request.session:
            del request.session[self.session_key]
            request.session.modified = True
        return Response(status=status.HTTP_204_NO_CONTENT)

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"detail": "El mensaje no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        role = determine_user_role(user)
        history = list(self._load_history(request))

        if is_prompt_injection_attempt(message):
            warning = (
                "No puedo procesar esa solicitud porque intenta manipular las "
                "instrucciones internas del asistente. Formula una pregunta sobre "
                "tickets, métricas o preguntas frecuentes."
            )

            history.append({"author": "user", "message": message})
            history.append({"author": "assistant", "message": warning})

            if len(history) > self.max_history:
                history = history[-self.max_history :]

            request.session[self.session_key] = history
            request.session.modified = True

            return Response({"answer": warning, "conversation": history})

        try:
            context = build_chat_context(user, message)
        except Exception:  # pragma: no cover - fallback defensivo
            logger.exception("Fallo al construir contexto para chatbot", exc_info=True)
            context = (
                "No se pudo generar el contexto dinámico, pero el bot puede informar"
                " sobre tickets y métricas generales según el rol del usuario."
            )

        answer = call_ai_api(context, message, role, history=history)

        history.append({"author": "user", "message": message})
        history.append({"author": "assistant", "message": answer})

        if len(history) > self.max_history:
            history = history[-self.max_history :]

        request.session[self.session_key] = history
        request.session.modified = True

        return Response({"answer": answer, "conversation": history})

