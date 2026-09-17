from rest_framework.throttling import SimpleRateThrottle


class PhoneOrIPRateThrottle(SimpleRateThrottle):
    scope = "otp"

    def get_cache_key(self, request, view):
        phone = (request.data.get("phone") or "").strip() if hasattr(request, "data") else ""
        if phone:
            ident = f"phone:{phone}"
        else:
            ident = f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class OTPSendRateThrottle(PhoneOrIPRateThrottle):
    scope = "otp_send"


class OTPVerifyRateThrottle(PhoneOrIPRateThrottle):
    scope = "otp_verify"
