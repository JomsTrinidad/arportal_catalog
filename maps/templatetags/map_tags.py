from django import template

register = template.Library()

@register.filter
def getattr_safe(obj, name):
    return getattr(obj, name, "")

@register.filter
def get_item(d, k):
    try:
        return d.get(k, "")
    except Exception:
        return ""

@register.filter
def longer_than(value, n=30):
    """Return True if the string length > n (default 30)."""
    try:
        return len(str(value)) > int(n)
    except Exception:
        return False

# --- string_XX accessors ---

@register.simple_tag
def string_value(obj, i):
    """
    Tag usage:
      {% string_value row 3 %}            -> renders string_03
      {% string_value row 3 as val %}     -> assigns to 'val'
    """
    try:
        idx = int(i)
    except Exception:
        return ""
    return getattr(obj, f"string_{idx:02d}", "")

@register.filter(name="string_value")
def string_value_filter(obj, i):
    """
    Filter usage:
      {{ row|string_value:3 }}            -> renders string_03
      {% with val=row|string_value:3 %}   -> assigns to 'val'
    """
    try:
        idx = int(i)
    except Exception:
        return ""
    return getattr(obj, f"string_{idx:02d}", "")
