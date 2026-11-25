import logging
import threading
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from .courier_check import fetch_courier_stats
from .models import CourierCheckLog, CourierCheckSettings
from .utils import normalize_bd_phone

logger = logging.getLogger(__name__)

RETRY_AFTER_ERROR = timedelta(minutes=2)
RETRY_DELAY_SECONDS = 150
_RETRY_PENDING = set()
_RETRY_LOCK = threading.Lock()


def should_auto_check(normalized, cfg) -> bool:
    if not (cfg.is_enabled and cfg.auto_check_new_numbers and (cfg.api_key or "").strip()):
        return False
    if CourierCheckLog.objects.filter(phone=normalized, is_error=False).exists():
        return False
    now = timezone.now()
    if CourierCheckLog.objects.filter(phone=normalized, is_error=True, created_at__gte=now - RETRY_AFTER_ERROR).exists():
        return False
    limit = int(cfg.auto_check_hourly_limit or 0)
    if limit and CourierCheckLog.objects.filter(source="auto", created_at__gte=now - timedelta(hours=1)).count() >= limit:
        return False
    return True


def _run(normalized):
    try:
        fetch_courier_stats(normalized, source="auto")
    except Exception:
        logger.exception("Auto courier check failed")
    finally:
        connection.close()


def _start(normalized):
    threading.Thread(target=_run, args=(normalized,), name="courier-auto-check", daemon=True).start()


def schedule_auto_check(phone):
    try:
        normalized = normalize_bd_phone(phone)
        if not normalized:
            return
        if not should_auto_check(normalized, CourierCheckSettings.get_solo()):
            return
        transaction.on_commit(lambda: _start(normalized))
    except Exception:
        logger.exception("Could not schedule the auto courier check")


def _retry_later(normalized):
    try:
        if should_auto_check(normalized, CourierCheckSettings.get_solo()):
            fetch_courier_stats(normalized, source="auto")
    except Exception:
        logger.exception("Courier retry after a failed check did not work")
    finally:
        with _RETRY_LOCK:
            _RETRY_PENDING.discard(normalized)
        connection.close()


def schedule_retry_after_failure(phone):
    try:
        normalized = normalize_bd_phone(phone)
        cfg = CourierCheckSettings.get_solo()
        if not normalized or not (cfg.is_enabled and cfg.auto_check_new_numbers and (cfg.api_key or "").strip()):
            return
        with _RETRY_LOCK:
            if normalized in _RETRY_PENDING:
                return
            _RETRY_PENDING.add(normalized)
        timer = threading.Timer(RETRY_DELAY_SECONDS, _retry_later, args=(normalized,))
        timer.daemon = True
        timer.start()
    except Exception:
        logger.exception("Could not schedule the retry after a failed courier check")
