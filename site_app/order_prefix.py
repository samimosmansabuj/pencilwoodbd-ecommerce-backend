import re

DEFAULT_ORDER_PREFIX = "PWBD"
MAX_PREFIX_LENGTH = 10


def clean_prefix(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:MAX_PREFIX_LENGTH]


def suggest_order_prefix(company_name):
    words = re.findall(r"[A-Za-z0-9]+", company_name or "")
    parts = []
    for word in words:
        parts += re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", word)
    if not parts:
        return "ORD"
    if len(parts) == 1:
        return clean_prefix(parts[0][:3]) or "ORD"
    return clean_prefix("".join(p if p.isupper() and len(p) > 1 else p[0] for p in parts)) or "ORD"


def get_order_id_prefix():
    try:
        from .models import SiteContent
        site = SiteContent.objects.only("order_id_prefix").order_by("pk").first()
        return clean_prefix(site.order_id_prefix) or DEFAULT_ORDER_PREFIX if site else DEFAULT_ORDER_PREFIX
    except Exception:
        return DEFAULT_ORDER_PREFIX
