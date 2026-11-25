import logging
from decimal import Decimal

from django.utils import timezone

from order.models import OrderAttempt
from product.models import AddToCart

from .courier_check import retention_delta
from .models import CourierCheckSettings, CourierRestrictedAttempt

logger = logging.getLogger(__name__)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _order_lines(data, request):
    lines = []

    def add(pid, vid, qty):
        pid = _int_or_none(pid)
        if pid is None:
            return
        line = {"id": pid, "quantity": max(_int_or_none(qty) or 1, 1)}
        vid = _int_or_none(vid)
        if vid:
            line["variant_id"] = vid
        lines.append(line)

    for key in ("items", "products"):
        rows = data.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    add(row.get("product_id") or row.get("id"), row.get("variant_id"), row.get("quantity", 1))
            if lines:
                return lines

    if data.get("product_id"):
        add(data.get("product_id"), data.get("variant_id"), data.get("quantity", 1))
        return lines

    cart_ids = data.get("cart_ids")
    customer = getattr(getattr(request, "user", None), "customer_profile", None)
    if isinstance(cart_ids, list) and cart_ids and customer is not None:
        for ci in AddToCart.objects.filter(customer=customer, id__in=cart_ids):
            add(ci.product_id, ci.variant_id, ci.quantity)
    return lines


def record_restricted_attempt(request, phone, gate, source):
    try:
        data = request.data
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        pick = lambda key: data.get(key) or customer.get(key)
        lines = _order_lines(data, request)

        attempt = None
        if lines:
            incoming = {line["id"] for line in lines}
            for a in OrderAttempt.objects.filter(phone=phone).order_by("-updated_at"):
                if a.is_subset_of(incoming):
                    attempt = a
                    break
        else:
            flagged = CourierRestrictedAttempt.objects.filter(phone=phone).select_related("attempt").first()
            attempt = flagged.attempt if flagged else None

        fields = {
            "name": pick("name"), "address": pick("address"), "district": pick("district"),
            "utm_source": data.get("utm_source"), "utm_medium": data.get("utm_medium"),
            "utm_campaign": data.get("utm_campaign"),
        }
        if attempt:
            for key, value in fields.items():
                if value:
                    setattr(attempt, key, value)
            if lines:
                attempt.products = lines
            attempt.save()
        else:
            attempt = OrderAttempt.objects.create(
                phone=phone, products=lines,
                source=data.get("source") or ("checkout" if source == "ecom" else "landing"),
                **fields,
            )

        now = timezone.now()
        flag, created = CourierRestrictedAttempt.objects.get_or_create(
            attempt=attempt,
            defaults={"phone": phone, "ratio": gate.ratio, "limit": gate.limit, "source": source, "first_at": now, "last_at": now},
        )
        if not created:
            flag.times += 1
            flag.ratio, flag.limit, flag.source, flag.last_at = gate.ratio, gate.limit, source, now
            flag.save()
        return flag
    except Exception:
        logger.exception("Could not record the refused order as an attempt")
        return None


def restricted_watermark(cfg):
    marks = []
    if cfg.restricted_cleared_at:
        marks.append(cfg.restricted_cleared_at)
    if not cfg.restricted_expire_forever:
        marks.append(timezone.now() - retention_delta(cfg.restricted_expire_value, cfg.restricted_expire_unit))
    return max(marks) if marks else None


def restricted_new_count(cfg=None) -> int:
    cfg = cfg or CourierCheckSettings.get_solo()
    qs = CourierRestrictedAttempt.objects.all()
    mark = restricted_watermark(cfg)
    if mark:
        qs = qs.filter(last_at__gt=mark)
    return qs.count()


def clear_restricted_count():
    CourierCheckSettings.get_solo()
    CourierCheckSettings.objects.filter(pk=1).update(restricted_cleared_at=timezone.now())
