"""Custom math-related template filters."""
from django import template

register = template.Library()


@register.filter(name="abs")
def absolute_value(value):
    """Return the absolute value of the given number.

    The built-in Django template filters do not include ``abs``. This helper
    mirrors Python's :func:`abs` so templates can display negative durations as
    positive numbers.
    """
    try:
        return abs(value)
    except TypeError:
        return value
