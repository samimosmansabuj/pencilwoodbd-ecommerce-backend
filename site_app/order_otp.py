from urllib.parse import urlparse


from rest_framework import status
from rest_framework.response import Response

from authentication.utils import normalize_bd_phone
from site_app.models import OrderOTPSetting, OTPVerification


def detect_landing_source(request, cfg=None):
    cfg = cfg or OrderOTPSetting.get_solo()
    raw = request.META.get("HTTP_ORIGIN") or request.META.get("HTTP_REFERER") or ""
    host = (urlparse(raw).hostname or "").lower()
    internal = {h.strip().lower() for h in (cfg.internal_hosts or "").split(",") if h.strip()}
    return "landing" if host and host in internal else "external"


def order_otp_gate(request, phone, source, success_key="status", landing_code=None):
    cfg = OrderOTPSetting.get_solo()
    if source == "auto":
        source = detect_landing_source(request, cfg)
    if not cfg.is_required(source, landing_code):
        return None

    norm = normalize_bd_phone(phone) or phone
    code = str(request.data.get("otp_code") or "").strip()
    if code and norm:
        otp = OTPVerification.objects.filter(phone=norm).last()
        if otp and not otp.is_expired() and not otp.is_locked:
            if otp.otp == code:
                otp.delete()  # one-time use
                return None
            otp.register_failed_attempt()
    return Response(
        {success_key: False, "otp_required": True, "order_otp": True, "phone": norm, "message": "Please Verify Your OTP First."},
        status=status.HTTP_403_FORBIDDEN,
    )