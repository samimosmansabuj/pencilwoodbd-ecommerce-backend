import re
from django.db.models import Q
from pencilwoodbd.choices import STATUS

def normalize_bd_phone(phone: str) -> str:
    """
    Always returns 13-digit form: 8801XXXXXXXXX
    Accepts only real BD mobile numbers in these input shapes:
      - 01XXXXXXXXX          (11 digits)
      - 8801XXXXXXXXX        (13 digits)
      - +8801XXXXXXXXX       (with +, dashes, spaces allowed)
    Returns "" if the input doesn't reduce to a valid BD mobile number.
    """
    if not phone:
        return ""

    digits = re.sub(r"\D", "", str(phone))  # strip everything except digits

    if len(digits) < 11:
        return ""

    local = digits[-11:]  # last 11 digits = 01XXXXXXXXX

    if re.match(r"^01[3-9]\d{8}$", local):
        return "88" + local

    return ""

def phone_lookup_variants(phone: str):
    """Given a normalized 88-format phone, return both possible stored formats
    so lookups work even if some old rows weren't migrated."""
    normalized = normalize_bd_phone(phone)
    if not normalized:
        return []
    local = normalized[2:]  # strip leading "88"
    return [normalized, local]

# ============ IP / DEVICE ORDER TRACKING & BLOCKING ============

def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_client_identity(request):
    from .models import make_device_hash

    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    device_hash = make_device_hash(ip, user_agent)
    return ip, user_agent, device_hash


def check_is_blocked(ip, device_hash):
    from .models import BlockedIdentity
    from django.db.models import Q

    return BlockedIdentity.objects.filter(
        Q(ip_address=ip) | Q(device_hash=device_hash),
        is_active=True
    ).first()


def record_order_track(order, request):
    from .models import OrderTrackRecord

    ip, user_agent, device_hash = get_client_identity(request)
    try:
        OrderTrackRecord.objects.create(
            order=order,
            ip_address=ip,
            device_hash=device_hash,
            user_agent=user_agent[:1000] if user_agent else "",
            status_at_capture=order.status,
        )
    except Exception:
        pass


def evaluate_cancel_block(ip, device_hash, staff_user=None):
    from .models import OrderTrackRecord, BlockedIdentity, TrackSettings
    from order.models import Order

    settings_obj = TrackSettings.get_solo()
    if not settings_obj.is_auto_block_enabled:
        return None

    records = OrderTrackRecord.objects.filter(
        Q(ip_address=ip) | Q(device_hash=device_hash)
    ).select_related("order").order_by("-created_at")

    order_ids = list(records.values_list("order_id", flat=True).distinct())
    orders = Order.objects.filter(id__in=order_ids).order_by("-created_at")

    if settings_obj.mode == TrackSettings.ModeChoices.CONSECUTIVE:
        consecutive_cancels = 0
        for o in orders:
            if o.status == STATUS.CANCELLED:
                consecutive_cancels += 1
            elif o.status == STATUS.DELIVERED:
                break
        cancel_count = consecutive_cancels
    else:
        cancel_count = orders.filter(status=STATUS.CANCELLED).count()

    if cancel_count >= settings_obj.cancel_threshold:
        already_blocked = BlockedIdentity.objects.filter(
            Q(ip_address=ip) | Q(device_hash=device_hash), is_active=True
        ).first()
        if already_blocked:
            return already_blocked

        blocked = BlockedIdentity.objects.create(
            ip_address=ip,
            device_hash=device_hash,
            reason=BlockedIdentity.ReasonChoices.AUTO_CANCEL_LIMIT,
            note=f"Auto-blocked: {cancel_count} cancels ({settings_obj.mode} mode, threshold={settings_obj.cancel_threshold})",
            blocked_by=staff_user,
            cancel_count_at_block_time=cancel_count,
        )
        return blocked

    return None