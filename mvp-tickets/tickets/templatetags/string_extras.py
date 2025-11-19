"""Custom string-related template filters."""

from django import template


register = template.Library()


@register.filter(name="replace_substring")
def replace_substring(value, replacements):
    """Replace a substring using a comma-separated ``old,new`` definition.

    If the filter is used incorrectly (e.g., without a comma) or the value is
    ``None``, it safely returns the original value.
    """

    if value is None:
        return value

    try:
        old, new = replacements.split(",", 1)
    except ValueError:
        return value

    return str(value).replace(old, new)
