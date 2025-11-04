"""Endpoint del chatbot interno con permisos por rol."""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from .services_chat import build_chat_context, call_ai_api, determine_user_role


logger = logging.getLogger(__name__)


class ChatView(APIView):
    """Recibe preguntas del usuario y delega la respuesta a la API de IA."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"detail": "El mensaje no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        role = determine_user_role(user)

        try:
            context = build_chat_context(user, message)
        except Exception:  # pragma: no cover - fallback defensivo
            logger.exception("Fallo al construir contexto para chatbot", exc_info=True)
            context = (
                "No se pudo generar el contexto dinámico, pero el bot puede informar"
                " sobre tickets y métricas generales según el rol del usuario."
            )

        answer = call_ai_api(context, message, role)
        return Response({"answer": answer})

