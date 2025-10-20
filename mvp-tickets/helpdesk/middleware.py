"""
Propósito:
    Endurecer la capa HTTP detectando rutas y entradas maliciosas antes de que
    alcancen las vistas de Django.
API pública:
    ``PathFirewall`` e ``InputValidationMiddleware`` agregados en ``settings.MIDDLEWARE``.
Flujo de datos:
    Solicitud cruda → validaciones de ruta/entrada → request limpio → vistas.
Permisos:
    No altera permisos; únicamente decide si rechaza la petición con 400.
Decisiones de diseño:
    Se aplica un firewall de path simple y un filtro de patrones XSS sin alterar
    los datos originales para minimizar falsos positivos.
Riesgos:
    Patrones insuficientes podrían dejar pasar payloads nuevos; ajustarlos requiere
    revisar logs antes de endurecer reglas para no bloquear usuarios legítimos.
"""

from __future__ import annotations

import logging
import re

# PATH-FIREWALL: middleware global anti-LFI
from urllib.parse import unquote

from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponseBadRequest

# PATH-FIREWALL: middleware global anti-LFI
SAFE_PATH = re.compile(r"^[a-zA-Z0-9/_\-.~]*$")
SAFE_KEY = re.compile(r"^[a-zA-Z0-9._-]*$")
SAFE_VAL = re.compile(r"^[a-zA-Z0-9 .,_-]*$")


# PATH-FIREWALL: middleware global anti-LFI
def _decode_multi(s, times=3):
    out = s
    for _ in range(times):
        try:
            dec = unquote(out)
            if dec == out:
                break
            out = dec
        except Exception:
            break
    return out


class PathFirewall:
    """Reject traversal attempts and malformed paths before reaching Django."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw = (request.META.get("RAW_URI") or request.get_full_path()).split("?", 1)[0]
        path_dec = _decode_multi(raw)

        # Bloqueos duros
        raw_lower = raw.lower()
        if (
            ".." in path_dec
            or "\\" in path_dec
            or "\x00" in path_dec
            or ("%2e" in raw_lower)
            or ("%2f" in raw_lower)
            or ("%5c" in raw_lower)
        ):
            return HttpResponseBadRequest()

        # Allowlist de caracteres de ruta
        if not SAFE_PATH.fullmatch(path_dec):
            return HttpResponseBadRequest()

        # Validación simple de querystring
        for k, v in request.GET.lists():
            k_dec = _decode_multi(k)
            if not SAFE_KEY.fullmatch(k_dec):
                return HttpResponseBadRequest()
            for val in v:
                if not SAFE_VAL.fullmatch(_decode_multi(val)):
                    return HttpResponseBadRequest()

        return self.get_response(request)

logger = logging.getLogger(__name__)

_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"javascript:\s*", re.IGNORECASE),
    re.compile(r"\balert\s*\(", re.IGNORECASE),
)


class InputValidationMiddleware:
    """Reject requests containing clearly malicious input patterns.

    This middleware performs a lightweight validation on ``request.GET`` and
    ``request.POST`` to catch payloads that try to inject script tags or common
    XSS vectors.  We avoid mutating the values to prevent surprising behaviour
    for the rest of the stack; instead we fail fast by raising
    :class:`SuspiciousOperation` so Django returns a ``400`` response.
    """

    max_length = 4096

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._validate_querydict(request.GET, source="GET")
        self._validate_querydict(request.POST, source="POST")
        return self.get_response(request)

    def _validate_querydict(self, querydict, *, source: str) -> None:
        for key, values in querydict.lists():
            self._validate_value(key, source=f"{source} key")
            for value in values:
                if isinstance(value, str):
                    self._validate_value(value, source=f"{source} value")

    def _validate_value(self, value: str, *, source: str) -> None:
        if len(value) > self.max_length:
            logger.warning("Rejected %s for exceeding maximum length", source)
            raise SuspiciousOperation("Entrada demasiado extensa.")

        for pattern in _UNSAFE_PATTERNS:
            if pattern.search(value):
                logger.warning("Rejected %s because it matched unsafe pattern '%s'", source, pattern.pattern)
                raise SuspiciousOperation("Se detectó contenido potencialmente malicioso.")

