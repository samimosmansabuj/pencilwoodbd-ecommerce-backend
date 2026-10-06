from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone

from .models import ActivityEvent, EVENT_TYPE

FILTER_KEYS = ("q", "product", "variant", "event_type", "start_date", "end_date")


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def read_filters(request):
    f = {k: (request.GET.get(k) or "").strip() for k in FILTER_KEYS}
    if f["event_type"] and f["event_type"] not in EVENT_TYPE.values:
        f["event_type"] = ""
    if f["start_date"] and not _parse_date(f["start_date"]):
        f["start_date"] = ""
    if f["end_date"] and not _parse_date(f["end_date"]):
        f["end_date"] = ""
    return f


def event_filters_active(f):
    return any(f.get(k) for k in ("product", "variant", "event_type", "start_date", "end_date"))


def _product_q(text, prefix="product__"):
    return (
        Q(**{f"{prefix}name__icontains": text})
        | Q(**{f"{prefix}slug__icontains": text})
        | Q(**{f"{prefix}sku__icontains": text})
    )


def _variant_q(text):
    return (
        Q(variant_label__icontains=text)
        | Q(variant__sku__icontains=text)
        | Q(variant__barcode__icontains=text)
    )


def _event_text_q(text):
    q = (
        _product_q(text)
        | _variant_q(text)
        | Q(page_url__icontains=text)
        | Q(page_title__icontains=text)
        | Q(meta__query__icontains=text)
        | Q(ip_address__icontains=text)
        | Q(customer__name__icontains=text)
        | Q(customer__phone__icontains=text)
        | Q(customer__email__icontains=text)
        | Q(visitor__visitor_id__icontains=text)
    )
    return q


def apply_event_filters(events, f, include_text=True):
    if f.get("event_type"):
        events = events.filter(event_type=f["event_type"])

    if f.get("product"):
        events = events.filter(_product_q(f["product"]))

    if f.get("variant"):
        events = events.filter(_variant_q(f["variant"]))

    start = _parse_date(f.get("start_date"))
    end = _parse_date(f.get("end_date"))
    tz = timezone.get_current_timezone()
    if start:
        events = events.filter(created_at__gte=timezone.make_aware(datetime.combine(start, time.min), tz))
    if end:
        events = events.filter(created_at__lte=timezone.make_aware(datetime.combine(end, time.max), tz))

    if include_text and f.get("q"):
        events = events.filter(_event_text_q(f["q"]))

    return events


def visitor_text_q(text):
    matching_visitor_ids = ActivityEvent.objects.filter(
        _product_q(text) | _variant_q(text) | Q(meta__query__icontains=text)
        | Q(page_url__icontains=text) | Q(page_title__icontains=text)
    ).values("visitor_id")

    return (
        Q(customer__name__icontains=text)
        | Q(customer__phone__icontains=text)
        | Q(customer__second_phone__icontains=text)
        | Q(customer__whatsapp__icontains=text)
        | Q(customer__email__icontains=text)
        | Q(customer__user__email__icontains=text)
        | Q(customer__user__username__icontains=text)
        | Q(visitor_id__icontains=text)
        | Q(first_ip__icontains=text)
        | Q(last_ip__icontains=text)
        | Q(utm_source__icontains=text)
        | Q(utm_campaign__icontains=text)
        | Q(landing_url__icontains=text)
        | Q(referrer__icontains=text)
        | Q(user_agent__icontains=text)
        | Q(id__in=matching_visitor_ids)
    )
