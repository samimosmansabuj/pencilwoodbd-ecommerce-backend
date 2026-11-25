from decimal import Decimal

from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timesince import timesince

from .utils import normalize_bd_phone
from .models import CourierCheckLog
from .models import CourierCheckSettings


def _fmt(value):
    return f"{Decimal(value).normalize():f}"


def latest_log(normalized, memo=None):

    if memo is not None and normalized in memo:
        return memo[normalized]
    log = (
        CourierCheckLog.objects.filter(phone=normalized, is_error=False)
        .order_by("-created_at", "-id").first()
    )
    if memo is not None:
        memo[normalized] = log
    return log


def has_failed_check(normalized, memo=None):

    key = ("failed", normalized)
    if memo is not None and key in memo:
        return memo[key]
    failed = CourierCheckLog.objects.filter(phone=normalized, is_error=True).exists()
    if memo is not None:
        memo[key] = failed
    return failed


def describe(log, cfg):
    when = timezone.localtime(log.created_at)
    date_text = f"{when:%d %b %Y, %I:%M %p} ({timesince(log.created_at)} ago)"
    limit = Decimal(cfg.min_success_ratio)
    ratio = log.success_ratio
    eff_total = log.total_parcels + (log.rate_only_parcels or 0)

    if ratio is None or eff_total == 0:
        return {"text": "New", "css": "bg-secondary",
                "title": f"No courier history (new customer). Checked {date_text}", "date_text": date_text}

    detail = f"Success {log.success_parcels} / Total {log.total_parcels} (cancelled {log.cancelled_parcels})"
    for item in (log.courier_breakdown or []):
        if item.get("rate_only"):
            detail += (f". {item.get('name')}: rate only {_fmt(Decimal(str(item.get('reported_ratio') or 0)))}%, "
                       f"counted as ~{item.get('est_total')}+ parcels")
    gap = ratio - limit
    gap_text = f"{'+' if gap >= 0 else ''}{_fmt(gap)}"
    title = f"Checked {date_text}. {detail}. Limit {_fmt(limit)}% ({gap_text})"

    if eff_total < max(int(cfg.min_parcels_to_evaluate or 1), 1):
        return {"text": f"{_fmt(ratio)}%*", "css": "bg-light text-dark border",
                "title": title + f". Only {eff_total} parcel(s): below the minimum, so not restricted.",
                "date_text": date_text}
    if ratio < limit:
        css = "bg-danger"
    elif ratio < limit + Decimal(cfg.warn_margin):
        css = "bg-warning text-dark"
    else:
        css = "bg-success"
    return {"text": f"{_fmt(ratio)}%", "css": css, "title": title, "date_text": date_text}


def render_courier_badge(phone, cfg=None, memo=None, can_check=True, include_script=False):

    cfg = cfg or CourierCheckSettings.get_solo()
    if not cfg.show_badges or not phone:
        return ""
    normalized = normalize_bd_phone(phone)
    if not normalized:
        return ""

    log = latest_log(normalized, memo)
    if log:
        ctx = describe(log, cfg)
    else:
        if not (cfg.api_key or "").strip():
            return ""
        ctx = {"unchecked": True, "phone": normalized, "failed": has_failed_check(normalized, memo)}
    ctx["can_check"] = can_check
    ctx["include_script"] = include_script
    return render_to_string("db_courier_check/partial/partial_courier_badge.html", ctx)


def render_log_badge(log, cfg, include_script=False):
    ctx = describe(log, cfg)
    ctx["can_check"] = False
    ctx["include_script"] = include_script
    return render_to_string("db_courier_check/partial/partial_courier_badge.html", ctx)