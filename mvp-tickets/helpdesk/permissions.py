"""Utilities and reusable permission helpers for the helpdesk project.

This module centralises custom Django REST Framework permissions used to
protect the API layer.  The goal is to make the intent explicit and keep the
rules in one place so that future adjustments (e.g. tightening who can perform
write operations) can be done safely.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.roles import is_admin, is_tech


class AuthenticatedSafeMethodsOnlyForRequesters(BasePermission):
    """Allow authenticated access, restrict unsafe methods to privileged roles.

    * Any unauthenticated request is rejected immediately.
    * Safe methods (GET/HEAD/OPTIONS) are allowed for every authenticated user.
    * Unsafe methods (POST/PUT/PATCH/DELETE) require the user to be an
      administrator or technician.

    This keeps the API readable for requesters while ensuring that only users
    with operational responsibilities can perform mutating actions.
    """

    message = _("Solo personal autorizado puede modificar recursos a través de la API.")

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False

        if request.method in SAFE_METHODS:
            return True

        return is_admin(user) or is_tech(user)


def requires_privileged_role(user) -> bool:
    """Small helper to express the privileged role check in one place."""

    return is_admin(user) or is_tech(user)


class PrivilegedOnlyPermission(BasePermission):
    """Force any access (even read) to be limited to privileged roles."""

    message = _("Debe ser administrador o técnico para usar este recurso.")

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False

        return requires_privileged_role(user)

