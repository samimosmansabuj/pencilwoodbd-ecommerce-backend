import logging
from collections import namedtuple

from django.utils import timezone

from pencilwoodbd.choices import CAMPAIGN_STATUS, CATEGORY_PRODUCT_STATUS

from .models import Campaign, CampaignProduct, normalize_surface
from .pricing import (
    build_campaign_pricing, effective_switches, get_campaign_status, get_sold_units_map, resolve_line_price,
)
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


def apply_campaign_to_product_payload(request, product, payload, slug, surface=None):
    try:
        now = timezone.now()
        ctx = resolve_product_context(slug, product, now)
        payload["server_now"] = now.isoformat()
        if ctx.state != STATE_VALID:
            payload["campaign_notice"] = ctx.state
            return payload
        if not ctx.campaign.allows_surface(surface):
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


def auto_campaign_map(product_ids, surface, now=None):
    now = now or timezone.now()
    ids = {int(i) for i in product_ids if i is not None}
    if not ids:
        return {}
    key = normalize_surface(surface)
    campaigns = [
        c for c in Campaign.objects.filter(is_active=True, start_at__lte=now, end_at__gte=now)
        if key in (c.price_surfaces or [])
    ]
    if not campaigns:
        return {}
    rank = {c.id: i for i, c in enumerate(campaigns)}
    rows = list(
        CampaignProduct.objects
        .filter(
            campaign__in=campaigns, product_id__in=ids, is_active=True,
            product__status=CATEGORY_PRODUCT_STATUS.ACTIVE, product__is_gift_only=False,
        )
        .select_related("campaign", "product")
        .prefetch_related("variant_discounts")
    )
    sold = get_sold_units_map(rows)
    result = {}
    for cp in sorted(rows, key=lambda r: rank[r.campaign_id]):
        if cp.product_id in result:
            continue
        if cp.stock_limit is not None and sold.get(cp.id, 0) >= cp.stock_limit:
            continue
        result[cp.product_id] = cp
    return result


def auto_campaign_slug(product, surface, now=None):
    cp = auto_campaign_map([product.id], surface, now).get(product.id)
    return cp.campaign.slug if cp else None


def apply_auto_campaign_to_product_payload(request, product, payload, surface):
    try:
        cp = auto_campaign_map([product.id], surface).get(product.id)
        if cp is None:
            return payload
        switches = effective_switches(cp.campaign, cp)
        payload["server_now"] = timezone.now().isoformat()
        payload["campaign_pricing"] = build_campaign_pricing(cp.campaign, cp, product)
        payload["campaign_surface"] = normalize_surface(surface).lower()
        payload.update(gift_fields(product, switches, request))
    except Exception:
        logger.exception("auto campaign failed for product=%s", getattr(product, "id", None))
        for key in ("campaign_pricing", "campaign_surface", "gift_product", "has_gift", "server_now"):
            payload.pop(key, None)
    return payload


def listing_campaign_fields(products, surface):
    try:
        found = auto_campaign_map([p.id for p in products], surface)
        out = {}
        for p in products:
            cp = found.get(p.id)
            if cp is None:
                continue
            line = resolve_line_price(cp.campaign, cp, p).as_public()
            out[p.id] = {
                "campaign_slug": cp.campaign.slug,
                "campaign_surface": normalize_surface(surface).lower(),
                "campaign_price": line["campaign_price"],
                "strike_price": line["strike_price"],
                "badge_text": line["badge_text"],
            }
        return out
    except Exception:
        logger.exception("listing campaign fields failed")
        return {}
