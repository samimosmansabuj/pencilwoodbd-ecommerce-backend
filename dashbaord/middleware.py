import hashlib
import json
import time

from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme

WINDOW = 30  # seconds
SESSION_KEY = "_dup_guard"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
EXEMPT_PREFIXES = ("/api/", "/admin/", "/static/", "/media/")
EXEMPT_CONTAINS = ("login", "logout", "otp", "webhook", "toggle", "send_message", "chat")
IGNORED_FIELDS = {"csrfmiddlewaretoken"}
MAX_BODY = 1024 * 1024

DUP_MESSAGE = (
    "This action was already submitted a moment ago, so the duplicate was ignored. "
    "Please check the list before trying again."
)


def _fingerprint(request):
    h = hashlib.sha1()
    has_data = False
    ctype = (request.content_type or "").lower()

    if ctype.startswith("multipart/") or ctype.startswith("application/x-www-form-urlencoded"):
        for key in sorted(request.POST.keys()):
            if key in IGNORED_FIELDS:
                continue
            for val in request.POST.getlist(key):
                h.update(f"{key}={val}\x00".encode("utf-8", "ignore"))
                has_data = True
        for key in sorted(request.FILES.keys()):
            for f in request.FILES.getlist(key):
                h.update(f"file:{key}:{f.name}:{f.size}\x00".encode("utf-8", "ignore"))
                has_data = True
    else:
        try:
            body = request.body
        except Exception:
            return None
        if body and len(body) <= MAX_BODY:
            h.update(body)
            has_data = True

    return h.hexdigest() if has_data else None


def _wants_json(request):
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("HX-Request") == "true"
        or "application/json" in request.headers.get("Accept", "")
        or "json" in (request.content_type or "")
    )


def _failed(request, response):
    if response.status_code >= 400:
        return True
    storage = getattr(request, "_messages", None)
    for m in getattr(storage, "_queued_messages", []) or []:
        if m.level >= messages.ERROR:
            return True
    if "json" in (response.get("Content-Type", "") or "") and not getattr(response, "streaming", False):
        try:
            data = json.loads(response.content.decode("utf-8"))
            if isinstance(data, dict) and (data.get("status") is False or data.get("success") is False):
                return True
        except Exception:
            pass
    return False


class DuplicateSubmitGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method not in WRITE_METHODS
            or not getattr(request, "user", None)
            or not request.user.is_authenticated
            or request.path.startswith(EXEMPT_PREFIXES)
            or any(s in request.path.lower() for s in EXEMPT_CONTAINS)
        ):
            return self.get_response(request)

        fp = _fingerprint(request)
        if fp is None:
            return self.get_response(request)

        key = request.get_full_path()
        now = time.time()
        guard = {k: v for k, v in (request.session.get(SESSION_KEY) or {}).items() if now - v[1] < WINDOW}

        last = guard.get(key)
        if last and last[0] == fp:
            return self._duplicate_response(request)

        guard[key] = [fp, now]
        request.session[SESSION_KEY] = guard
        request.session.modified = True

        try:
            response = self.get_response(request)
        except Exception:
            self._forget(request, key, fp)
            raise

        if _failed(request, response):
            self._forget(request, key, fp)
        return response

    @staticmethod
    def _forget(request, key, fp):
        guard = request.session.get(SESSION_KEY) or {}
        if guard.get(key) and guard[key][0] == fp:
            guard.pop(key, None)
            request.session[SESSION_KEY] = guard
            request.session.modified = True

    @staticmethod
    def _duplicate_response(request):
        if _wants_json(request):
            resp = JsonResponse(
                {"status": False, "success": False, "duplicate": True, "message": DUP_MESSAGE},
                status=409,
            )
            if request.headers.get("HX-Request") == "true":
                resp["HX-Reswap"] = "none"
            return resp
        messages.warning(request, DUP_MESSAGE)
        back = request.META.get("HTTP_REFERER")
        if not back or not url_has_allowed_host_and_scheme(back, {request.get_host()}):
            back = "/"
        return HttpResponseRedirect(back)