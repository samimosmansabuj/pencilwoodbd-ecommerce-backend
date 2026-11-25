import logging
from collections import namedtuple

from django.utils import timezone

from pencilwoodbd.choices import CAMPAIGN_STATUS

from .models import Campaign, CampaignProduct
from .pricing import build_campaign_pricing, effective_switches, get_campaign_status
from product.serializers import ProductGiftingSerializer

logger = logging.getLogger("pencilwoodbd")

NOTICE_ENDED = "ended"
NOTICE_NOT_IN_CAMPAIGN = "not_in_campaign"
NOTICE_NOT_STARTED = "not_started"

STATE_VALID = "valid"

ProductContext = namedtuple("ProductContext", ["state", "campaign", "campaign_product"])


def resolve_product_context(slug, product, now=None):
    now = now or timezone.now()
    campaign = Campaign.objects.filter(slug=slug).first() if slug else None
    if campaign is None:
        return ProductContext(NOTICE_NOT_IN_CAMPAIGN, None, None)

    status = get_campaign_status(campaign, now)
    if status == CAMPAIGN_STATUS.DRAFT:
        return ProductContext(NOTICE_NOT_IN_CAMPAIGN, None, None)
    if status == CAMPAIGN_STATUS.ENDED:
        return ProductContext(NOTICE_ENDED, campaign, None)
    if status == CAMPAIGN_STATUS.UPCOMING:
        return ProductContext(NOTICE_NOT_STARTED, campaign, None)

    campaign_product = (
        CampaignProduct.objects
        .filter(campaign=campaign, product=product, is_active=True)
        .prefetch_related("variant_discounts")
        .first()
    )
    if campaign_product is None:
        return ProductContext(NOTICE_NOT_IN_CAMPAIGN, campaign, None)
    return ProductContext(STATE_VALID, campaign, campaign_product)


def gift_fields(product, switches, request=None, gifts=None):
    if not switches.gifts_included:
        return {"gift_product": [], "has_gift": False}

    if gifts is None:
        gifts = list(product.gift_product.select_related("gift_product"))
    data = ProductGiftingSerializer(gifts, many=True, context={"request": request}).data
    return {"gift_product": data, "has_gift": bool(data)}


def apply_campaign_to_product_payload(request, product, payload, slug):
    try:
        now = timezone.now()
        ctx = resolve_product_context(slug, product, now)
        payload["server_now"] = now.isoformat()
        if ctx.state != STATE_VALID:
            payload["campaign_notice"] = ctx.state
            return payload

        switches = effective_switches(ctx.campaign, ctx.campaign_product)
        payload["campaign_pricing"] = build_campaign_pricing(ctx.campaign, ctx.campaign_product, product)
        payload.update(gift_fields(product, switches, request))
    except Exception:  # pragma: no cover - defensive
        logger.exception("campaign context failed for product=%s slug=%s", getattr(product, "id", None), slug)
        for key in ("campaign_pricing", "campaign_notice", "gift_product", "has_gift", "server_now"):
            payload.pop(key, None)
    return payload


def offers_suppressed(slug, product, now=None):
    if not slug:
        return False
    ctx = resolve_product_context(slug, product, now)
    if ctx.state != STATE_VALID:
        return False
    return not effective_switches(ctx.campaign, ctx.campaign_product).offers_included
