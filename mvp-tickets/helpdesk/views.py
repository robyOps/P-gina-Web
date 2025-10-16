"""Auxiliary views for global error handling."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger(__name__)


def _resolve_safe_redirect(request: HttpRequest) -> str:
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return referer

    return reverse("dashboard")


def redirect_to_safe_location(request: HttpRequest, exception=None):
    """Handle 404 errors by redirecting the user to a safe location."""

    target = _resolve_safe_redirect(request)
    if exception:
        logger.warning("Página no encontrada: %s (%s)", request.path, exception)

    messages.warning(request, "La página solicitada no existe. Te redirigimos al panel.")
    return redirect(target)


def handle_server_error(request: HttpRequest):
    """Gracefully recover from server errors by redirecting to the dashboard."""

    logger.error("Error interno del servidor al procesar %s", request.path)
    messages.error(request, "Ocurrió un error inesperado. Hemos vuelto al panel principal.")
    return redirect(_resolve_safe_redirect(request))

