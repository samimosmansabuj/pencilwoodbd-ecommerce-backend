from django import template

from authentication.courier_badge import render_courier_badge, render_log_badge
from authentication.courier_restricted import restricted_new_count
from authentication.models import CourierCheckSettings
from authentication.views import COURIER_ROLES

register = template.Library()


def _memo(context):
    rc = context.render_context
    if "_courier_memo" not in rc:
        rc["_courier_memo"] = {"cfg": None, "logs": {}, "script_done": False}
    return rc["_courier_memo"]


@register.simple_tag(takes_context=True)
def courier_badge(context, phone):

    memo = _memo(context)
    if memo["cfg"] is None:
        memo["cfg"] = CourierCheckSettings.get_solo()
    request = context.get("request")
    user = getattr(request, "user", None)
    can_check = True if user is None else getattr(user, "user_type", None) in COURIER_ROLES
    html = render_courier_badge(phone, cfg=memo["cfg"], memo=memo["logs"], can_check=can_check,
                                include_script=not memo["script_done"])
    if html:
        memo["script_done"] = True
    return html


@register.simple_tag(takes_context=True)
def courier_log_badge(context, log):

    memo = _memo(context)
    if memo["cfg"] is None:
        memo["cfg"] = CourierCheckSettings.get_solo()
    html = render_log_badge(log, memo["cfg"], include_script=not memo["script_done"])
    memo["script_done"] = True
    return html


@register.simple_tag
def restricted_attempt_count():
    return restricted_new_count()
