"""Custom password validators for the accounts app."""

from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ComplexPasswordValidator:
    """Require a mix of characters to harden account passwords."""

    uppercase_pattern = re.compile(r"[A-ZÁÉÍÓÚÜÑ]")
    lowercase_pattern = re.compile(r"[a-záéíóúüñ]")
    digit_pattern = re.compile(r"\d")
    symbol_pattern = re.compile(r"[^\w\s]")

    def validate(self, password: str, user: Any = None) -> None:  # noqa: D401
        errors: list[str] = []
        if not self.uppercase_pattern.search(password):
            errors.append(_("Debe contener al menos una letra mayúscula."))
        if not self.lowercase_pattern.search(password):
            errors.append(_("Debe contener al menos una letra minúscula."))
        if not self.digit_pattern.search(password):
            errors.append(_("Debe contener al menos un número."))
        if not self.symbol_pattern.search(password):
            errors.append(_("Debe contener al menos un símbolo."))

        if errors:
            raise ValidationError(errors)

    def get_help_text(self) -> str:
        return _(
            "La contraseña debe incluir letras mayúsculas, minúsculas, números y símbolos."
        )

