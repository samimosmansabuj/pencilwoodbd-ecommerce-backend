from collections import namedtuple
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.utils import timezone

from pencilwoodbd.choices import (
    CAMPAIGN_BADGE_MODE,
    CAMPAIGN_DISCOUNT_TYPE,
    CAMPAIGN_PRICE_SOURCE,
    CAMPAIGN_STATUS,
    CAMPAIGN_SWITCH_MODE,
    CAMPAIGN_VARIANT_MODE,
    STATUS,
)
from django.db.models import Sum
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

NON_COUNTING_ORDER_STATUSES = (STATUS.CANCELLED,)

WARN_NO_VISIBLE_DISCOUNT = "no_visible_discount"
WARN_ABOVE_CURRENT_PRICE = "above_current_price"
WARN_VARIANT_DISCOUNT_MISSING = "variant_discount_missing"
WARN_INVALID_DISCOUNT_VALUE = "invalid_discount_value"
WARN_NO_ACTIVE_VARIANT = "no_active_variant"


def to_decimal(value, default=ZERO):
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def round_half_up(value):
    return to_decimal(value).quantize(ONE, rounding=ROUND_HALF_UP)


def num(value):
    if value is None:
        return None
    value = to_decimal(value)
    if value == value.to_integral_value():
        return int(value)
    return float(round(value, 2))


def active_variants(product):
    if not product.has_variants:
        return []
    return sorted((v for v in product.variants.all() if v.is_active), key=lambda v: (not v.is_default, v.id))


def get_campaign_status(campaign, now=None):
    now = now or timezone.now()
    if not campaign.is_active:
        return CAMPAIGN_STATUS.DRAFT
    if now < campaign.start_at:
        return CAMPAIGN_STATUS.UPCOMING
    if now <= campaign.end_at:
        return CAMPAIGN_STATUS.LIVE
    return CAMPAIGN_STATUS.ENDED


def is_live(campaign, now=None):
    return get_campaign_status(campaign, now) == CAMPAIGN_STATUS.LIVE


def find_overlap_conflicts(campaign, product_ids=None):
    if not campaign.is_active or not campaign.start_at or not campaign.end_at:
        return []

    CampaignProduct = apps.get_model("campaigns", "CampaignProduct")

    if product_ids is None:
        if not campaign.pk:
            return []
        product_ids = list(
            CampaignProduct.objects.filter(campaign=campaign, is_active=True).values_list("product_id", flat=True)
        )
    product_ids = list(product_ids)
    if not product_ids:
        return []

    qs = (
        CampaignProduct.objects
        .filter(
            product_id__in=product_ids,
            is_active=True,
            campaign__is_active=True,
            campaign__start_at__lte=campaign.end_at,
            campaign__end_at__gte=campaign.start_at,
            # an ended campaign is finished: it never blocks the same products in a new campaign
            campaign__end_at__gt=timezone.now(),
        )
        .select_related("campaign", "product")
        .order_by("campaign__start_at", "id")
    )
    if campaign.pk:
        qs = qs.exclude(campaign_id=campaign.pk)

    conflicts = []
    for row in qs:
        if campaign.allow_overlap and row.campaign.allow_overlap:
            continue
        conflicts.append({
            "product_id": row.product_id,
            "product_name": row.product.name,
            "campaign_id": row.campaign_id,
            "campaign_title": row.campaign.title,
            "campaign_slug": row.campaign.slug,
            "start_at": row.campaign.start_at,
            "end_at": row.campaign.end_at,
        })
    return conflicts


def validate_no_overlap(campaign, product_ids=None):
    conflicts = find_overlap_conflicts(campaign, product_ids)
    if conflicts:
        lines = [
            f"'{c['product_name']}' is already in the overlapping campaign '{c['campaign_title']}'"
            for c in conflicts
        ]
        raise ValidationError(
            lines + ["Turn on 'allow overlap' on BOTH campaigns or change the dates."]
        )


EffectiveSwitches = namedtuple("EffectiveSwitches", ["gifts_included", "offers_included"])


def _switch(mode, campaign_default):
    if mode == CAMPAIGN_SWITCH_MODE.INCLUDE:
        return True
    if mode == CAMPAIGN_SWITCH_MODE.EXCLUDE:
        return False
    return bool(campaign_default)


def effective_switches(campaign, campaign_product):
    return EffectiveSwitches(
        gifts_included=_switch(campaign_product.gift_mode, campaign.include_product_gifts),
        offers_included=_switch(campaign_product.offer_mode, campaign.include_offers),
    )


@dataclass
class LinePrice:
    variant_id: Optional[int]
    regular: Decimal
    current: Decimal
    base: Decimal
    campaign_price: Decimal
    strike: Optional[Decimal]
    savings_amount: Decimal
    savings_percent: int
    badge_text: Optional[str]
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    has_visible_discount: bool = False
    warnings: List[str] = field(default_factory=list)

    def as_public(self):
        return {
            "regular_price": num(self.regular),
            "current_price": num(self.current),
            "campaign_price": num(self.campaign_price),
            "strike_price": num(self.strike),
            "savings_amount": num(self.savings_amount),
            "savings_percent": self.savings_percent,
            "badge_text": self.badge_text,
        }


def effective_price_sources(campaign, campaign_product):
    return (
        campaign_product.discount_base_override or campaign.discount_base,
        campaign_product.strike_price_override or campaign.strike_price_display,
    )


def _discount_for_line(campaign_product, variant):
    if campaign_product.variant_mode == CAMPAIGN_VARIANT_MODE.PER_VARIANT and variant is not None:
        for row in campaign_product.variant_discounts.all():
            if row.variant_id == variant.id:
                return row.discount_type, row.discount_value
        return None
    return campaign_product.discount_type, campaign_product.discount_value


def _valid_discount(discount_type, value):
    if discount_type == CAMPAIGN_DISCOUNT_TYPE.PERCENT:
        return ZERO < value < HUNDRED
    if discount_type == CAMPAIGN_DISCOUNT_TYPE.FIXED:
        return value > ZERO
    return False


def resolve_line_price(campaign, campaign_product, product, variant=None):
    if product.has_variants:
        variant = variant or product.display_variant
        if variant is None:
            return LinePrice(
                variant_id=None, regular=ZERO, current=ZERO, base=ZERO, campaign_price=ZERO, strike=None,
                savings_amount=ZERO, savings_percent=0, badge_text=None, warnings=[WARN_NO_ACTIVE_VARIANT],
            )
        source = variant
    else:
        variant = None
        source = product

    regular = to_decimal(source.price)
    own_discount = to_decimal(source.discount_price)
    current = own_discount if own_discount > ZERO else regular
    discount_base, strike_display = effective_price_sources(campaign, campaign_product)
    base = regular if discount_base == CAMPAIGN_PRICE_SOURCE.REGULAR else current

    warnings = []
    discount = _discount_for_line(campaign_product, variant)
    discount_type = discount_value = None

    if discount is None:
        campaign_price = current
        warnings.append(WARN_VARIANT_DISCOUNT_MISSING)
    else:
        discount_type, discount_value = discount[0], to_decimal(discount[1])
        if not _valid_discount(discount_type, discount_value):
            warnings.append(WARN_INVALID_DISCOUNT_VALUE)
        if discount_type == CAMPAIGN_DISCOUNT_TYPE.PERCENT:
            raw = base * (HUNDRED - discount_value) / HUNDRED
        else:
            raw = base - discount_value
        campaign_price = max(round_half_up(raw), ZERO)

    strike_basis = regular if strike_display == CAMPAIGN_PRICE_SOURCE.REGULAR else current
    visible = discount is not None and strike_basis > ZERO and campaign_price < strike_basis

    strike = savings_amount = None
    savings_percent = 0
    badge_text = None
    if visible:
        strike = strike_basis
        savings_amount = round_half_up(strike_basis - campaign_price)
        savings_percent = int(round_half_up(savings_amount / strike_basis * HUNDRED))
        if discount_type == CAMPAIGN_DISCOUNT_TYPE.PERCENT:
            badge_text = f"{savings_percent}% OFF"
        else:
            badge_text = f"৳{int(savings_amount)} OFF"
        if campaign.badge_mode == CAMPAIGN_BADGE_MODE.NAME_AND_DISCOUNT:
            label = (campaign.badge_label or campaign.title or "").strip()
            if label:
                badge_text = f"{label} · {badge_text}"
    else:
        savings_amount = ZERO
        if discount is not None:
            warnings.append(WARN_NO_VISIBLE_DISCOUNT)

    if discount is not None and campaign_price > current:
        warnings.append(WARN_ABOVE_CURRENT_PRICE)

    return LinePrice(
        variant_id=variant.id if variant is not None else None,
        regular=regular, current=current, base=base, campaign_price=campaign_price,
        strike=strike, savings_amount=savings_amount, savings_percent=savings_percent, badge_text=badge_text,
        discount_type=discount_type, discount_value=discount_value,
        has_visible_discount=visible, warnings=warnings,
    )


def order_items_track_campaigns():
    try:
        apps.get_model("order", "OrderItem")._meta.get_field("campaign")
        return True
    except (LookupError, FieldDoesNotExist):
        return False


def get_sold_units_map(campaign_products):
    campaign_products = list(campaign_products)
    result = {cp.id: 0 for cp in campaign_products}
    if not campaign_products or not order_items_track_campaigns():
        return result

    OrderItem = apps.get_model("order", "OrderItem")
    rows = (
        OrderItem.objects
        .filter(
            campaign_id__in={cp.campaign_id for cp in campaign_products},
            product_id__in={cp.product_id for cp in campaign_products},
        )
        .exclude(order__status__in=NON_COUNTING_ORDER_STATUSES)
        .values("campaign_id", "product_id")
        .annotate(units=Sum("quantity"))
    )
    sold = {(r["campaign_id"], r["product_id"]): int(r["units"] or 0) for r in rows}
    for cp in campaign_products:
        result[cp.id] = sold.get((cp.campaign_id, cp.product_id), 0)
    return result


def get_sold_units(campaign_product):
    return get_sold_units_map([campaign_product])[campaign_product.id]


def stock_left_for(campaign_product, sold_units=None):
    if campaign_product.stock_limit is None:
        return None
    if sold_units is None:
        sold_units = get_sold_units(campaign_product)
    return max(campaign_product.stock_limit - sold_units, 0)


def get_campaign_sales_stats(campaign_ids=None):
    if not order_items_track_campaigns():
        return {}

    OrderItem = apps.get_model("order", "OrderItem")
    qs = OrderItem.objects.filter(campaign__isnull=False).exclude(order__status__in=NON_COUNTING_ORDER_STATUSES)
    if campaign_ids is not None:
        qs = qs.filter(campaign_id__in=list(campaign_ids))
    rows = qs.values("campaign_id").annotate(
        orders=Count("order_id", distinct=True),
        units=Sum("quantity"),
        revenue=Sum(ExpressionWrapper(F("discount_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2))),
    )
    return {
        r["campaign_id"]: {"orders": r["orders"], "units": int(r["units"] or 0), "revenue": r["revenue"] or ZERO}
        for r in rows
    }


def build_campaign_pricing(campaign, campaign_product, product, sold_units=None):
    top = resolve_line_price(campaign, campaign_product, product)
    switches = effective_switches(campaign, campaign_product)

    variants = []
    for variant in active_variants(product):
        line = resolve_line_price(campaign, campaign_product, product, variant)
        variants.append({"variant_id": variant.id, **line.as_public()})

    return {
        "campaign_slug": campaign.slug,
        **top.as_public(),
        "stock_limit": campaign_product.stock_limit,
        "stock_left": stock_left_for(campaign_product, sold_units),
        "gifts_included": switches.gifts_included,
        "offers_included": switches.offers_included,
        "variants": variants,
    }