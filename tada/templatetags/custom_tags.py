from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    value = dictionary.get(str(key), 0)
    return value if value is not None else 0


@register.filter
def abs_value(value):
    try:
        return abs(int(value))
    except:
        return 0


@register.filter
def div(value, arg):
    try:
        return float(value) / float(arg)
    except:
        return 0


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return 0
