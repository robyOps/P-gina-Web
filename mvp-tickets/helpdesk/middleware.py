"""Custom middleware used to harden request handling."""

from __future__ import annotations

import logging
import re

from django.core.exceptions import SuspiciousOperation

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

