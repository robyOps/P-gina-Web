"""Timezone helpers centralised for the project."""

from __future__ import annotations

from datetime import tzinfo

from django.conf import settings
from django.utils import timezone

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    from backports.zoneinfo import ZoneInfo  # type: ignore


def _resolve_timezone() -> tzinfo:
    tz_name = getattr(settings, "TIME_ZONE", None) or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:  # pragma: no cover - defaults when zoneinfo fails
        return timezone.get_default_timezone()


LOCAL_TIMEZONE = _resolve_timezone()


def get_local_timezone() -> tzinfo:
    """Return the configured local timezone for analytics visualisations."""

    return LOCAL_TIMEZONE

