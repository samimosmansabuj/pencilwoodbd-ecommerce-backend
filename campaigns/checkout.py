from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from django.utils import timezone

from pencilwoodbd.choices import CAMPAIGN_STATUS, CATEGORY_PRODUCT_STATUS
from product.models import customization_extra

from .models import Campaign, CampaignProduct
from .pricing import (
    LinePrice,
    ZERO,
    effective_switches,
    get_campaign_status,
    get_sold_units_map,
    num,
    effective_price_sources,
    resolve_line_price,
    to_decimal,
)

REASON_ENDED = "campaign_ended"
REASON_PAUSED = "campaign_paused"
REASON_NOT_STARTED = "campaign_not_started"
REASON_NOT_FOUND = "campaign_not_found"
REASON_PRODUCT_REMOVED = "product_removed"
REASON_STOCK_EXHAUSTED = "stock_exhausted"
REASON_QUANTITY_EXCEEDS = "quantity_exceeds_remaining"

REASON_MESSAGES = {
    REASON_ENDED: "এই ক্যাম্পেইনটি শেষ হয়ে গেছে / This campaign has ended",
    REASON_PAUSED: "ক্যাম্পেইনটি এখন চালু নেই / This campaign is not running right now",
    REASON_NOT_STARTED: "ক্যাম্পেইনটি এখনো শুরু হয়নি / This campaign has not started yet",
    REASON_NOT_FOUND: "ক্যাম্পেইনটি আর পাওয়া যাচ্ছে না / This campaign is no longer available",
    REASON_PRODUCT_REMOVED: "পণ্যটি আর এই ক্যাম্পেইনে নেই / This product is no longer in the campaign",
    REASON_STOCK_EXHAUSTED: "ক্যাম্পেইন স্টক শেষ হয়ে গেছে / The campaign stock is sold out",
    REASON_QUANTITY_EXCEEDS: "ক্যাম্পেইন মূল্যে আর মাত্র {remaining}টি আছে / Only {remaining} left at the campaign price",
}

COUPON_CAMPAIGN_MESSAGE = "এই কুপন ক্যাম্পেইন পণ্যে প্রযোজ্য নয় / This coupon can't be used on campaign items"


def reason_message(reason, remaining=None):
    return REASON_MESSAGES.get(reason, reason or "").format(remaining=remaining if remaining is not None else 0)


def normal_prices(product, variant):
    source = variant if variant is not None else product
    regular = to_decimal(source.price)
    discount = to_decimal(source.discount_price)
    return regular, (discount if discount else regular)


@dataclass
class LineResult:
    line_id: Any
    product: Any
    variant: Any
    quantity: int
    campaign_slug: Optional[str]
    regular: Decimal = ZERO
    current: Decimal = ZERO
    extra: Decimal = ZERO
    campaign: Any = None
    campaign_product: Any = None
    line_price: Optional[LinePrice] = None
    valid: bool = True
    reason: Optional[str] = None
    remaining: Optional[int] = None
    gifts_included: bool = True
    offers_included: bool = True
    coupon_allowed: bool = True

    @property
    def is_campaign_line(self):
        return bool(self.campaign_slug)

    @property
    def applies(self):
        return self.is_campaign_line and self.valid and self.line_price is not None

    @property
    def unit_price(self):
        return self.line_price.campaign_price if self.applies else self.current

    @property
    def final_unit_price(self):
        return self.unit_price + self.extra

    @property
    def regular_unit_price(self):
        return self.regular + self.extra

    @property
    def line_total(self):
        return self.final_unit_price * self.quantity


def resolve_lines(lines, now=None, lock=False):
    now = now or timezone.now()
    slugs = {l.get("campaign_slug") for l in lines if l.get("campaign_slug")}
    campaigns = {c.slug: c for c in Campaign.objects.filter(slug__in=slugs)} if slugs else {}
    lines = [
        {**l, "campaign_slug": None}
        if l.get("campaign_slug") in campaigns and not campaigns[l["campaign_slug"]].allows_surface(l.get("surface"))
        else l
        for l in lines
    ]

    cp_map = {}
    if campaigns:
        qs = CampaignProduct.objects.filter(
            campaign__in=list(campaigns.values()),
            product_id__in={l["product"].id for l in lines if l.get("campaign_slug")},
        )
        if lock:
            qs = qs.select_for_update().order_by("id")
        for cp in qs.prefetch_related("variant_discounts"):
            cp_map[(cp.campaign_id, cp.product_id)] = cp
    sold_map = get_sold_units_map(cp_map.values()) if cp_map else {}

    results, wanted = [], {}
    for line in lines:
        product, variant = line["product"], line.get("variant")
        regular, current = normal_prices(product, variant)
        r = LineResult(
            line_id=line.get("line_id"), product=product, variant=variant,
            quantity=int(line.get("quantity") or 0), campaign_slug=line.get("campaign_slug") or None,
            regular=regular, current=current,
            extra=customization_extra(product, line.get("is_customized"), variant),
        )
        results.append(r)
        if not r.is_campaign_line:
            continue

        campaign = campaigns.get(r.campaign_slug)
        if campaign is None:
            r.valid, r.reason = False, REASON_NOT_FOUND
            continue
        r.campaign = campaign

        cp = cp_map.get((campaign.id, product.id))
        if cp is not None:
            r.campaign_product = cp
            r.line_price = resolve_line_price(campaign, cp, product, variant)

        status = get_campaign_status(campaign, now)
        if status == CAMPAIGN_STATUS.DRAFT:
            r.valid, r.reason = False, REASON_PAUSED
        elif status == CAMPAIGN_STATUS.ENDED:
            r.valid, r.reason = False, REASON_ENDED
        elif status == CAMPAIGN_STATUS.UPCOMING:
            r.valid, r.reason = False, REASON_NOT_STARTED
        elif (cp is None or not cp.is_active or product.status != CATEGORY_PRODUCT_STATUS.ACTIVE
              or product.is_gift_only):
            r.valid, r.reason = False, REASON_PRODUCT_REMOVED
        else:
            wanted[cp.id] = wanted.get(cp.id, 0) + r.quantity

    for r in results:
        cp = r.campaign_product
        if cp is None or not r.is_campaign_line:
            continue
        if cp.stock_limit is not None:
            r.remaining = max(cp.stock_limit - sold_map.get(cp.id, 0), 0)
        if not r.valid:
            continue
        if r.remaining is not None:
            if r.remaining <= 0:
                r.valid, r.reason = False, REASON_STOCK_EXHAUSTED
            elif wanted.get(cp.id, 0) > r.remaining:
                r.valid, r.reason = False, REASON_QUANTITY_EXCEEDS

    for r in results:
        if r.applies:
            switches = effective_switches(r.campaign, r.campaign_product)
            r.gifts_included = switches.gifts_included
            r.offers_included = switches.offers_included
            r.coupon_allowed = bool(r.campaign.allow_coupon)
    return results


def campaign_unit_price_for_cart_line(campaign, product, variant, now=None):
    now = now or timezone.now()
    if get_campaign_status(campaign, now) != CAMPAIGN_STATUS.LIVE:
        return None
    cp = CampaignProduct.objects.filter(campaign=campaign, product=product, is_active=True).prefetch_related(
        "variant_discounts").first()
    if cp is None:
        return None
    return resolve_line_price(campaign, cp, product, variant).campaign_price


def invalid_lines(results):
    return [r for r in results if r.is_campaign_line and not r.valid]


def price_changed_payload(results):
    bad = invalid_lines(results)
    if not bad:
        return None
    return {
        "status": False,
        "success": False,
        "code": "price_changed",
        "message": "কিছু ক্যাম্পেইন মূল্য বদলে গেছে, কার্ট দেখে আবার অর্ডার করুন / "
                   "Some campaign prices have changed. Please review your cart and place the order again.",
        "lines": [
            {
                "line_id": r.line_id,
                "product_id": r.product.id,
                "variant_id": r.variant.id if r.variant is not None else None,
                "product": r.product.name,
                "campaign": r.campaign_slug,
                "reason": r.reason,
                "message": reason_message(r.reason, r.remaining),
                "new_unit_price": num(r.current + r.extra),
                "campaign_unit_price": num(r.line_price.campaign_price + r.extra) if r.line_price else None,
                "remaining": r.remaining,
            }
            for r in bad
        ],
    }


def coupon_split(results):
    eligible = [r for r in results if r.coupon_allowed]
    excluded = [r for r in results if not r.coupon_allowed]
    return eligible, excluded


def coupon_exclusion_note(excluded):
    campaigns = sorted({r.campaign.title for r in excluded if r.campaign is not None})
    return {
        "note": "Coupon was not applied on campaign items (campaign setting)",
        "campaigns": campaigns,
        "excluded_subtotal": num(sum((r.line_total for r in excluded), ZERO)),
    }


def offer_engine_lines(rows):
    return [
        {"product_id": row["product_id"], "variant_id": row.get("variant_id"), "quantity": row["quantity"]}
        for row in rows
        if row.get("offers_included") is not False
    ]


def line_pricing_payload(r):
    if not r.is_campaign_line:
        return {"campaign": None}
    data = {
        "campaign": r.campaign_slug,
        "campaign_title": r.campaign.title if r.campaign is not None else None,
        "campaign_valid": r.valid,
        "campaign_reason": r.reason,
        "campaign_message": reason_message(r.reason, r.remaining) if not r.valid else None,
        "campaign_stock_left": r.remaining,
        "normal_unit_price": num(r.current + r.extra),
    }
    if r.line_price is not None:
        lp = r.line_price
        data.update({
            "regular_price": num(lp.regular),
            "current_price": num(lp.current),
            "campaign_price": num(lp.campaign_price),
            "strike_price": num(lp.strike),
            "savings_amount": num(lp.savings_amount),
            "savings_percent": lp.savings_percent,
            "badge_text": lp.badge_text,
            "gifts_included": r.gifts_included if r.applies else None,
            "offers_included": r.offers_included if r.applies else None,
        })
    return data


def order_item_campaign_fields(r):
    if not r.applies:
        return {}
    lp, source = r.line_price, (r.variant if r.variant is not None else r.product)
    return {
        "campaign": r.campaign,
        "campaign_name": r.campaign.title,
        "regular_price": lp.regular,
        "product_sale_price": to_decimal(source.discount_price),
        "base_price_used": lp.base,
        "campaign_discount_type": lp.discount_type,
        "campaign_discount_value": lp.discount_value,
        "campaign_savings_amount": lp.savings_amount,
        "campaign_savings_percent": lp.savings_percent,
    }


def campaign_snapshot(r):
    if not r.applies:
        return {}
    lp, c = r.line_price, r.campaign
    return {
        "campaign": {"id": c.id, "slug": c.slug, "title": c.title},
        "campaign_pricing": {
            "regular_price": num(lp.regular),
            "current_price": num(lp.current),
            "base_price_used": num(lp.base),
            "campaign_price": num(lp.campaign_price),
            "strike_price": num(lp.strike),
            "savings_amount": num(lp.savings_amount),
            "savings_percent": lp.savings_percent,
            "badge_text": lp.badge_text,
            "discount_type": lp.discount_type,
            "discount_value": num(lp.discount_value),
            "discount_base": effective_price_sources(c, r.campaign_product)[0],
            "strike_price_display": effective_price_sources(c, r.campaign_product)[1],
            "variant_id": lp.variant_id,
            "warnings": list(lp.warnings),
        },
        "campaign_gifts_included": bool(r.gifts_included),
        "campaign_offers_included": bool(r.offers_included),
        "campaign_coupon_allowed": bool(r.coupon_allowed),
    }
