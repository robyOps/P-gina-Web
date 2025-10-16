"""
===============================================================================
Propósito:
    API mínima para exponer información del usuario autenticado.
API pública:
    ``MeView`` con método ``GET`` sobre ``/api/auth/me/`` retornando datos del
    usuario actual.
Flujo de datos:
    Request autenticada → ``MeView.get`` → acceso a ``request.user`` →
    ``Response`` JSON.
Dependencias:
    Django REST Framework y el modelo de usuario configurado en el proyecto.
Decisiones:
    Se limita la respuesta a campos básicos y nombres de grupos para evitar
    filtrar datos sensibles.
TODOs:
    TODO:PREGUNTA Confirmar si es necesario exponer permisos explícitos además
    de los grupos.
===============================================================================
"""

from rest_framework.views import APIView
from rest_framework.response import Response


class MeView(APIView):
    """Devuelve datos básicos del usuario autenticado utilizando autenticación DRF."""

    def get(self, request):
        """Retorna identificador, username, email y grupos asociados.

        La vista confía en que el middleware de autenticación ya asignó un
        ``request.user`` válido. No se hacen consultas adicionales más allá de
        los ``groups`` para mantener el endpoint ligero.
        """

        u = request.user
        groups = list(u.groups.values_list("name", flat=True))
        return Response({"id": u.id, "username": u.username, "email": u.email, "groups": groups})
