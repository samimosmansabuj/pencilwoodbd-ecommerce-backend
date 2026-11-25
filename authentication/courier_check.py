import logging
import re
import threading
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from urllib.parse import quote

import requests
from django.utils import timezone

from pencilwoodbd.choices import CourierLowRatioActionChoices, DEFAULT_COURIER_HARD_BLOCK_MESSAGE
from .utils import normalize_bd_phone
from .models import CourierCheckLog
from .models import CourierCheckSettings, CourierCheckLog, CourierNumberRetention
from .models import CourierCheckSettings, CourierNumberRetention
from .models import CourierCheckSettings, CourierCheckLog
from site_app.models import ContactInformation
from .models import CourierCheckSettings
from .utils import get_or_verify_otp_override

logger = logging.getLogger(__name__)

TOTAL_KEYS = ("total_parcel", "total_parcels", "total_orders", "total", "parcels")
SUCCESS_KEYS = (
    "success_parcel", "success_parcels", "delivered_parcel", "delivered_parcels",
    "delivered", "success", "completed",
)
CANCEL_KEYS = (
    "cancelled_parcel", "cancelled_parcels", "canceled_parcel", "canceled_parcels",
    "cancelled", "canceled", "returned_parcel", "returned",
)
NON_COURIER_KEYS = {"summary", "total", "overall", "meta", "reports"}


def _to_int(value) -> int:
    try:
        return max(int(float(value)), 0)
    except (TypeError, ValueError):
        return 0


def _first_present(block: dict, keys):
    for k in keys:
        if k in block and block[k] is not None:
            return block[k]
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _to_decimal_percent(value) -> Optional[Decimal]:
    try:
        d = Decimal(str(value))
    except Exception:
        return None
    return d if Decimal("0") <= d <= Decimal("100") else None


def _range_floor(parcel_range) -> int:
    m = re.search(r"\d+", str(parcel_range or ""))
    return max(int(m.group()), 1) if m else 1


def _ratio(success, total) -> Optional[Decimal]:
    if total <= 0:
        return None
    return (Decimal(success) * 100 / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class CourierStat:
    slug: str
    name: str
    total: int = 0
    success: int = 0
    cancelled: int = 0
    rate_only: bool = False
    reported_ratio: Optional[Decimal] = None
    est_total: int = 0
    est_success: Decimal = Decimal("0")

    @property
    def ratio(self):
        if self.rate_only:
            return self.reported_ratio
        return _ratio(self.success, self.total)

    def as_dict(self):
        r = self.ratio
        return {
            "slug": self.slug, "name": self.name, "total": self.total,
            "success": self.success, "cancelled": self.cancelled,
            "ratio": float(r) if r is not None else None,
            "rate_only": self.rate_only,
            "reported_ratio": float(self.reported_ratio) if self.reported_ratio is not None else None,
            "est_total": self.est_total,
            "est_success": float(self.est_success),
        }


@dataclass
class CourierCheckResult:
    ok: bool = False
    total: int = 0
    success: int = 0
    cancelled: int = 0
    couriers: List[CourierStat] = field(default_factory=list)
    reports: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    error: str = ""
    from_cache: bool = False
    checked_at: Optional[datetime] = None
    est_total: int = 0
    est_success: Decimal = Decimal("0")
    stale: bool = False

    @property
    def eval_total(self):
        return self.total + self.est_total

    @property
    def eval_success(self):
        return Decimal(self.success) + self.est_success

    @property
    def ratio(self):
        return _ratio(self.eval_success, self.eval_total)


def parse_courier_payload(payload, ignored_slugs=()) -> CourierCheckResult:
    result = CourierCheckResult(raw=payload if isinstance(payload, dict) else {})
    if not isinstance(payload, dict):
        result.error = "Unexpected response from courier API."
        return result

    status = str(payload.get("status", "")).lower()
    if status and status not in ("success", "ok", "true", "200"):
        result.error = str(payload.get("message") or payload.get("error") or "Courier API returned an error.")
        return result

    data = payload.get("data")
    ignored = {_slug(s) for s in ignored_slugs if s}

    entries = []
    if isinstance(data, dict):
        for key, block in data.items():
            if key in NON_COURIER_KEYS or not isinstance(block, dict):
                continue
            entries.append((key, block))
    elif isinstance(data, list):
        for block in data:
            if isinstance(block, dict):
                entries.append((block.get("slug") or block.get("name") or block.get("courier") or "", block))

    for key, block in entries:
        total_raw = _first_present(block, TOTAL_KEYS)
        if total_raw is None:
            continue
        name = block.get("name") or block.get("courier") or str(key).title()
        slug = _slug(key or name)
        if slug in ignored or _slug(name) in ignored:
            continue
        total = _to_int(total_raw)
        success = _to_int(_first_present(block, SUCCESS_KEYS))
        cancel_raw = _first_present(block, CANCEL_KEYS)
        cancelled = _to_int(cancel_raw) if cancel_raw is not None else max(total - success, 0)
        stat = CourierStat(slug=slug, name=str(name), total=total, success=success, cancelled=cancelled)
        if block.get("rate_only") and total == 0:
            reported = _to_decimal_percent(block.get("success_ratio"))
            if reported is not None:
                stat.rate_only = True
                stat.reported_ratio = reported
                stat.est_total = _range_floor(block.get("parcel_range"))
                stat.est_success = Decimal(stat.est_total) * reported / Decimal(100)
        result.couriers.append(stat)

    if result.couriers:
        result.total = sum(c.total for c in result.couriers)
        result.success = sum(c.success for c in result.couriers)
        result.cancelled = sum(c.cancelled for c in result.couriers)
        result.est_total = sum(c.est_total for c in result.couriers)
        result.est_success = sum((c.est_success for c in result.couriers), Decimal("0"))
    elif isinstance(data, dict) and isinstance(data.get("summary"), dict) and not ignored:
        s = data["summary"]
        result.total = _to_int(_first_present(s, TOTAL_KEYS))
        result.success = _to_int(_first_present(s, SUCCESS_KEYS))
        cancel_raw = _first_present(s, CANCEL_KEYS)
        result.cancelled = _to_int(cancel_raw) if cancel_raw is not None else max(result.total - result.success, 0)

    reports = payload.get("reports")
    if isinstance(reports, list):
        result.reports = reports[:20]

    result.ok = True
    return result


class BaseCourierProvider:
    key = "base"
    label = "Base"

    def __init__(self, cfg):
        self.cfg = cfg

    def fetch(self, phone_local: str) -> CourierCheckResult:
        raise NotImplementedError


class BdCourierProvider(BaseCourierProvider):
    key = "bdcourier"
    label = "BDCourier"

    def fetch(self, phone_local: str) -> CourierCheckResult:
        cfg = self.cfg
        api_key = (cfg.api_key or "").strip()
        if not api_key:
            return CourierCheckResult(error="BDCourier API key is not set.")

        url = f"{(cfg.api_base_url or '').rstrip('/')}/{(cfg.api_endpoint or '').lstrip('/')}"
        read_timeout = max(int(cfg.timeout_seconds or 8), 1)
        connect_timeout = min(read_timeout, 4)
        tries = 1 + min(max(int(getattr(cfg, "api_retries", 0) or 0), 0), 3)
        deadline = time.monotonic() + read_timeout + 8
        resp = None
        last_exc = None
        for attempt in range(tries):
            try:
                resp = requests.post(
                    url,
                    json={"phone": phone_local},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=(connect_timeout, read_timeout),
                )
                break
            except (requests.ConnectionError, requests.ReadTimeout) as exc:
                last_exc = exc
                logger.warning("BDCourier request failed (try %s of %s): %s", attempt + 1, tries, exc)
                if attempt + 1 < tries and time.monotonic() + 0.5 < deadline:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                break
            except requests.RequestException as exc:
                logger.warning("BDCourier request failed: %s", exc)
                return CourierCheckResult(error=f"Could not reach BDCourier: {exc.__class__.__name__}")
        if resp is None:
            return CourierCheckResult(error=f"Could not reach BDCourier: {last_exc.__class__.__name__} (tried {attempt + 1}x)")

        try:
            body = resp.json()
        except ValueError:
            return CourierCheckResult(error=f"BDCourier returned non-JSON (HTTP {resp.status_code}).")

        if resp.status_code >= 400:
            msg = ""
            if isinstance(body, dict):
                msg = str(body.get("message") or body.get("error") or "")
            if resp.status_code in (401, 403):
                msg = msg or "BDCourier rejected the API key (invalid, expired or no access)."
            elif resp.status_code == 429:
                msg = msg or "BDCourier request limit reached. Check your BDCourier plan."
            return CourierCheckResult(raw=body if isinstance(body, dict) else {}, error=msg or f"BDCourier HTTP {resp.status_code}")

        return parse_courier_payload(body, cfg.ignored_courier_list())


PROVIDERS = {BdCourierProvider.key: BdCourierProvider}


def _result_from_log(log) -> CourierCheckResult:
    couriers = []
    for c in (log.courier_breakdown or []):
        reported = c.get("reported_ratio")
        couriers.append(CourierStat(
            c["slug"], c["name"], c["total"], c["success"], c["cancelled"],
            rate_only=bool(c.get("rate_only")),
            reported_ratio=Decimal(str(reported)) if reported is not None else None,
            est_total=int(c.get("est_total") or 0),
            est_success=Decimal(str(c.get("est_success") or 0)),
        ))
    return CourierCheckResult(
        ok=True,
        total=log.total_parcels,
        success=log.success_parcels,
        cancelled=log.cancelled_parcels,
        couriers=couriers,
        reports=log.reports or [],
        raw=log.raw_response or {},
        from_cache=True,
        checked_at=log.created_at,
        est_total=sum(c.est_total for c in couriers),
        est_success=sum((c.est_success for c in couriers), Decimal("0")),
    )


def _save_log(normalized, provider, source, result):
    try:
        return CourierCheckLog.objects.create(
            phone=normalized,
            provider=provider,
            source=(source or "")[:20],
            is_error=not result.ok,
            error_message=(result.error or "")[:500],
            total_parcels=result.total,
            success_parcels=result.success,
            cancelled_parcels=result.cancelled,
            rate_only_parcels=result.est_total,
            success_ratio=result.ratio,
            courier_breakdown=[c.as_dict() for c in result.couriers],
            reports=result.reports,
            raw_response=result.raw or {},
        )
    except Exception:
        logger.exception("Could not save courier check log")
        return None


UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
AUTO_PURGE_EVERY = timedelta(hours=6)


def retention_delta(value, unit) -> timedelta:
    return timedelta(days=max(int(value or 1), 1) * UNIT_DAYS.get(unit, 1))


def retention_label(forever, value, unit) -> str:
    if forever:
        return "Forever"
    value = int(value or 1)
    return f"{value} {unit}{'' if value == 1 else 's'}"


def describe_keep(cfg, rule=None) -> dict:
    if rule is not None:
        return {"text": retention_label(rule.keep_forever, rule.value, rule.unit), "custom": True}
    return {"text": retention_label(cfg.retention_forever, cfg.retention_value, cfg.retention_unit), "custom": False}


def purge_expired_logs(cfg=None, dry_run=False) -> int:

    cfg = cfg or CourierCheckSettings.get_solo()
    now = timezone.now()
    total = 0

    def run(qs):
        return qs.count() if dry_run else qs.delete()[0]

    if not cfg.retention_forever:
        cutoff = now - retention_delta(cfg.retention_value, cfg.retention_unit)
        qs = CourierCheckLog.objects.filter(created_at__lt=cutoff).exclude(
            phone__in=CourierNumberRetention.objects.values("phone")
        )
        total += run(qs)

    for rule in CourierNumberRetention.objects.filter(keep_forever=False):
        cutoff = now - retention_delta(rule.value, rule.unit)
        total += run(CourierCheckLog.objects.filter(phone=rule.phone, created_at__lt=cutoff))
    return total


def maybe_auto_purge(cfg):

    try:
        if cfg.last_cleanup_at and timezone.now() - cfg.last_cleanup_at < AUTO_PURGE_EVERY:
            return
        CourierCheckSettings.objects.filter(pk=cfg.pk).update(last_cleanup_at=timezone.now())
        if (not cfg.retention_forever) or CourierNumberRetention.objects.filter(keep_forever=False).exists():
            purge_expired_logs(cfg)
    except Exception:
        logger.exception("Courier history auto-cleanup failed")


_INFLIGHT = {}
_INFLIGHT_LOCK = threading.Lock()


def fetch_courier_stats(phone: str, cfg=None, source: str = "", use_cache: bool = True, allow_stale: bool = True) -> CourierCheckResult:

    cfg = cfg or CourierCheckSettings.get_solo()
    normalized = normalize_bd_phone(phone)
    if not normalized:
        return CourierCheckResult(error="Invalid Bangladeshi mobile number.")
    local = normalized[2:]

    if use_cache and cfg.cache_hours:
        since = timezone.now() - timedelta(hours=cfg.cache_hours)
        cached = (
            CourierCheckLog.objects.filter(phone=normalized, is_error=False, created_at__gte=since, provider=cfg.provider)
            .order_by("-created_at", "-id").first()
        )
        if cached:
            return _result_from_log(cached)

    with _INFLIGHT_LOCK:
        event = _INFLIGHT.get(normalized)
        mine = event is None
        if mine:
            event = _INFLIGHT[normalized] = threading.Event()
    if not mine:
        waited_from = timezone.now() - timedelta(seconds=2)
        event.wait(timeout=max(int(cfg.timeout_seconds or 8), 1) + 8)
        fresh = (
            CourierCheckLog.objects.filter(phone=normalized, is_error=False, created_at__gte=waited_from, provider=cfg.provider)
            .order_by("-created_at", "-id").first()
        )
        if fresh and use_cache:
            return _result_from_log(fresh)

    try:
        provider_cls = PROVIDERS.get(cfg.provider, BdCourierProvider)
        try:
            result = provider_cls(cfg).fetch(local)
        except Exception as exc:
            logger.exception("Courier provider crashed")
            result = CourierCheckResult(error=f"Courier check crashed: {exc.__class__.__name__}")

        result.checked_at = timezone.now()
        _save_log(normalized, cfg.provider, source, result)
    finally:
        if mine:
            with _INFLIGHT_LOCK:
                _INFLIGHT.pop(normalized, None)
            event.set()
    maybe_auto_purge(cfg)

    if not result.ok and allow_stale:
        last = (
            CourierCheckLog.objects.filter(phone=normalized, is_error=False, provider=cfg.provider)
            .order_by("-created_at", "-id").first()
        )
        if last:
            old = _result_from_log(last)
            old.stale = True
            return old
    return result


def is_low_ratio(result: CourierCheckResult, cfg) -> bool:
    if not result.ok:
        return not cfg.fail_open
    if result.eval_total < max(int(cfg.min_parcels_to_evaluate or 0), 1):
        return False
    ratio = result.ratio
    return ratio is not None and ratio < Decimal(cfg.min_success_ratio)


@dataclass
class GateResult:
    otp_verified: bool = False
    response: Optional[dict] = None
    status_code: int = 200
    restricted: bool = False
    ratio: Optional[Decimal] = None
    limit: Optional[Decimal] = None


def get_support_whatsapp(cfg) -> str:
    raw = (cfg.whatsapp_number or "").strip()
    if not raw:
        try:
            contact = ContactInformation.objects.first()
            raw = (contact.whatspp_number or contact.phone or "") if contact else ""
        except Exception:
            raw = ""
    normalized = normalize_bd_phone(raw)
    return normalized or re.sub(r"\D", "", raw)


def is_hard_blocked(result: CourierCheckResult, cfg) -> bool:
    if not cfg.hard_block_enabled or not result.ok:
        return False
    if result.eval_total < max(int(cfg.min_parcels_to_evaluate or 0), 1):
        return False
    ratio = result.ratio
    return ratio is not None and ratio < Decimal(cfg.hard_block_ratio)


def get_hard_block_contact(cfg) -> str:
    return (cfg.hard_block_contact or "").strip() or get_support_whatsapp(cfg)


def build_hard_block_message(cfg) -> str:
    text = (cfg.hard_block_message or "").strip() or DEFAULT_COURIER_HARD_BLOCK_MESSAGE
    limit = f"{Decimal(cfg.hard_block_ratio).normalize():f}"
    return text.replace("{limit}", limit).replace("{contact}", get_hard_block_contact(cfg))


def courier_gate(phone: str, source: str, otp_code=None) -> GateResult:

    cfg = CourierCheckSettings.get_solo()
    if not cfg.is_enabled or not (cfg.api_key or "").strip() or not phone:
        return GateResult()
    if source == "ecom" and not cfg.apply_on_ecom:
        return GateResult()
    if source == "landing" and not cfg.apply_on_landing:
        return GateResult()

    result = fetch_courier_stats(phone, cfg=cfg, source=source, allow_stale=False)
    if not result.ok:
        from .courier_auto import schedule_retry_after_failure
        schedule_retry_after_failure(phone)

    if is_hard_blocked(result, cfg):
        return GateResult(
            response={
                "blocked": True,
                "otp_required": False,
                "contact_whatsapp": False,
                "courier_low_ratio": True,
                "courier_restricted": True,
                "contact_number": get_hard_block_contact(cfg),
                "limit": float(cfg.hard_block_ratio),
                "message": build_hard_block_message(cfg),
            },
            status_code=403,
            restricted=True,
            ratio=result.ratio,
            limit=Decimal(cfg.hard_block_ratio),
        )

    if not is_low_ratio(result, cfg):
        return GateResult()

    if cfg.low_ratio_action == CourierLowRatioActionChoices.WHATSAPP:
        number = get_support_whatsapp(cfg)
        prefill = (cfg.whatsapp_prefill_text or "").replace("{phone}", str(phone))
        text = quote(prefill)
        return GateResult(
            response={
                "blocked": True,
                "otp_required": False,
                "contact_whatsapp": True,
                "courier_low_ratio": True,
                "whatsapp_number": number,
                "whatsapp_url": (f"https://wa.me/{number}" + (f"?text={text}" if text else "")) if number else "",
                "message": cfg.whatsapp_message,
            },
            status_code=403,
        )

    if otp_code and get_or_verify_otp_override(phone, otp_code):
        return GateResult(otp_verified=True)
    return GateResult(
        response={
            "otp_required": True,
            "courier_low_ratio": True,
            "phone": phone,
            "message": cfg.otp_message,
        },
        status_code=403,
    )