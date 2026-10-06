from collections import OrderedDict
from datetime import datetime, time
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views import View

from authentication.models import Customer
from product.models import Product, ProductVariant
from .models import ActivityEvent, VisitorProfile, EVENT_TYPE

FILTER_KEYS = ("q", "product", "variant", "event_type", "start_date", "end_date")


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_filters(request):
    f = {k: (request.GET.get(k) or "").strip() for k in FILTER_KEYS}
    if f["event_type"] and f["event_type"] not in EVENT_TYPE.values:
        f["event_type"] = ""
    if f["start_date"] and not _parse_date(f["start_date"]):
        f["start_date"] = ""
    if f["end_date"] and not _parse_date(f["end_date"]):
        f["end_date"] = ""

    product_id = _to_int(f["product"])
    variant_id = _to_int(f["variant"])
    f["product"] = str(product_id) if product_id else ""
    f["variant"] = ""
    if product_id and variant_id and ProductVariant.objects.filter(pk=variant_id, product_id=product_id).exists():
        f["variant"] = str(variant_id)
    return f


def variant_label(variant):
    attrs = variant.attributes or {}
    label = ", ".join(f"{k}: {v}" for k, v in sorted(attrs.items()))
    return label or variant.sku or f"Variant #{variant.pk}"


def filter_options(f):
    products = Product.objects.order_by("name").only("id", "name", "slug")
    variants = []
    if f.get("product"):
        variants = [
            {"id": v.id, "label": variant_label(v)}
            for v in ProductVariant.objects.filter(product_id=f["product"]).order_by("id")
        ]
    return {"products": products, "variants": variants}


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
        events = events.filter(product_id=f["product"])

    if f.get("variant"):
        events = events.filter(variant_id=f["variant"])

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

def _querystring(filters, extra=None):
    data = {k: v for k, v in filters.items() if v}
    if extra:
        data.update({k: v for k, v in extra.items() if v})
    return urlencode(data)


class CustomerActivityView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        filters = read_filters(request)

        base_events = ActivityEvent.objects.filter(customer=customer)
        events = (
            apply_event_filters(base_events, filters)
            .select_related("product", "variant", "customer")
            .order_by("-created_at")
        )

        paginator = Paginator(events, 30)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "customer": customer,
            "events": page_obj,
            "paginator": paginator,
            "total_events": base_events.count(),
            "sessions": VisitorProfile.objects.filter(customer=customer).order_by("-last_seen"),
            "event_types": EVENT_TYPE.choices,
            "filters": filters,
            **filter_options(filters),
            "qs": _querystring(filters),
            "page_url": request.path,
            "target_id": "activity-tab-content",
            "empty_text": "No activity found for this customer.",
        }

        if request.htmx:
            return render(request, "db_tracking/partial/partial_activity_list.html", context)
        return render(request, "db_tracking/customer_activity.html", context)


class VisitorListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        filters = read_filters(request)
        guest_only = request.GET.get("guest_only") == "1"
        source = (request.GET.get("source") or "").strip()

        visitors = VisitorProfile.objects.select_related("customer").order_by("-last_seen")

        if guest_only:
            visitors = visitors.filter(customer__isnull=True)
        if source:
            visitors = visitors.filter(utm_source__icontains=source)

        events_filtered = event_filters_active(filters)
        if events_filtered:
            matching = apply_event_filters(ActivityEvent.objects.all(), filters, include_text=False)
            visitors = visitors.filter(id__in=matching.values("visitor_id"))

        if filters["q"]:
            visitors = visitors.filter(visitor_text_q(filters["q"]))

        paginator = Paginator(visitors, 30)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        if events_filtered:
            self._attach_matches(page_obj.object_list, filters)

        extra = {"guest_only": "1" if guest_only else "", "source": source}
        context = {
            "visitors": page_obj,
            "paginator": paginator,
            "filters": filters,
            **filter_options(filters),
            "guest_only": guest_only,
            "source": source,
            "events_filtered": events_filtered,
            "event_types": EVENT_TYPE.choices,
            "qs": _querystring(filters, extra),
            "page_url": request.path,
            "target_id": "visitor-tab-content",
        }

        if request.htmx:
            return render(request, "db_tracking/partial/partial_visitor_list.html", context)
        return render(request, "db_tracking/visitor_list.html", context)

    @staticmethod
    def _attach_matches(visitors, filters):
        visitors = list(visitors)
        ids = [v.id for v in visitors]
        events = (
            apply_event_filters(ActivityEvent.objects.filter(visitor_id__in=ids), filters, include_text=False)
            .select_related("product")
            .order_by("-created_at")
        )

        grouped = {v.id: OrderedDict() for v in visitors}
        for ev in events:
            key = (ev.product_id, ev.variant_label or "")
            bucket = grouped[ev.visitor_id].setdefault(key, {
                "product_name": ev.product.name if ev.product else "—",
                "product_slug": ev.product.slug if ev.product else "",
                "variant_label": ev.variant_label or "",
                "count": 0,
                "last": ev.created_at,
                "types": set(),
            })
            bucket["count"] += 1
            bucket["types"].add(ev.get_event_type_display())

        for v in visitors:
            items = list(grouped[v.id].values())
            for it in items:
                it["types"] = ", ".join(sorted(it["types"]))
            v.matches = items[:5]
            v.matches_more = max(len(items) - 5, 0)
            v.matched_total = sum(i["count"] for i in items)


class VisitorActivityView(LoginRequiredMixin, View):

    login_url = "admin_login"

    def get(self, request, pk):
        visitor = get_object_or_404(VisitorProfile.objects.select_related("customer"), pk=pk)
        filters = read_filters(request)

        base_events = ActivityEvent.objects.filter(visitor=visitor)
        events = (
            apply_event_filters(base_events, filters)
            .select_related("product", "variant", "customer")
            .order_by("-created_at")
        )

        paginator = Paginator(events, 30)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "visitor": visitor,
            "events": page_obj,
            "paginator": paginator,
            "total_events": base_events.count(),
            "event_types": EVENT_TYPE.choices,
            "filters": filters,
            **filter_options(filters),
            "qs": _querystring(filters),
            "page_url": request.path,
            "target_id": "visitor-activity-tab-content",
            "empty_text": "No activity found for this visitor.",
        }

        if request.htmx:
            return render(request, "db_tracking/partial/partial_visitor_activity_list.html", context)
        return render(request, "db_tracking/visitor_activity.html", context)
