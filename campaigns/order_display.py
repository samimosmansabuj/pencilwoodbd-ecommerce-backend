from decimal import Decimal

from pencilwoodbd.choices import CAMPAIGN_DISCOUNT_TYPE

ZERO = Decimal("0")
GIFT_OFFER_NOTE = "Gift/offer not applied (campaign setting)"

SOURCE_TEXT = {"SAME_FOR_ALL": "same charge for all products", "PRODUCT_WISE": "product-wise charge"}
BASIS_TEXT = {"PER_ORDER": "one charge per order", "PER_PRODUCT": "charge per product"}
SOURCE_RULE_TEXT = {
    "GLOBAL": "the global charge (product-wise charges ignored)",
    "LOWEST": "the lowest charge among the products in the cart",
    "HIGHEST": "the highest charge among the products in the cart",
}
MIXED_TEXT = {"COMBINED": "only the campaign charge (normal items add nothing)", "SEPARATE": "campaign charge + normal charge"}


def is_campaign_item(item):
    return bool(item.campaign_id or item.campaign_name)


def _discount_text(item):
    if item.campaign_discount_value is None:
        return ""
    value = item.campaign_discount_value
    value = int(value) if value == value.to_integral_value() else value.normalize()
    return f"{value}%" if item.campaign_discount_type == CAMPAIGN_DISCOUNT_TYPE.PERCENT else f"\u09F3{value}"


def item_savings_total(item):
    return (item.campaign_savings_amount or ZERO) * item.quantity


def attach_campaign_summary(orders):
    for order in orders:
        chips, seen, total = [], set(), ZERO
        if order.has_campaign:
            for item in order.order_items.all():
                if not is_campaign_item(item):
                    continue
                key = item.campaign_id or item.campaign_name
                if key not in seen:
                    seen.add(key)
                    chips.append({"id": item.campaign_id, "name": item.campaign_name or "Campaign"})
                total += item_savings_total(item)
        order.campaign_chips = chips
        order.campaign_discount_total = total
    return orders


def campaign_item_rows(order):
    rows = []
    for item in order.order_items.all():
        if not is_campaign_item(item):
            continue
        snap = item.snapshot or {}
        gifts_off = snap.get("campaign_gifts_included") is False
        offers_off = snap.get("campaign_offers_included") is False
        rows.append({
            "item": item,
            "campaign_name": item.campaign_name,
            "campaign_id": item.campaign_id,
            "regular_price": item.regular_price,
            "product_sale_price": item.product_sale_price,
            "discount_type": item.campaign_discount_type,
            "discount_text": _discount_text(item),
            "price_after": item.discount_price,
            "savings_amount": item.campaign_savings_amount,
            "savings_percent": item.campaign_savings_percent,
            "savings_total": item_savings_total(item),
            "gift_offer_note": GIFT_OFFER_NOTE if (gifts_off or offers_off) else "",
            "gifts_off": gifts_off,
            "offers_off": offers_off,
            "manually_edited": bool(item.price_manually_edited),
        })
    return rows


def _config_text(config):
    if not isinstance(config, dict) or not config:
        return ""
    parts = []
    for key, amount in config.items():
        label = "All districts" if key == "all" else str(key)
        parts.append(f"{label} \u09F3{amount}")
    return ", ".join(parts)


def delivery_view(order):
    bd = order.delivery_breakdown or {}
    if not order.has_campaign or not bd.get("groups"):
        return None
    groups = []
    for g in bd["groups"]:
        if g.get("type") == "campaign":
            rule = g.get("rule") or {}
            text = "Special campaign delivery: {}, {}, cart with normal items: {}".format(
                SOURCE_TEXT.get(rule.get("amount_source"), rule.get("amount_source") or "-"),
                BASIS_TEXT.get(rule.get("basis"), rule.get("basis") or "-"),
                MIXED_TEXT.get(rule.get("mixed_cart_delivery"), rule.get("mixed_cart_delivery") or "-"),
            )
            config = rule.get("config")
            config_text = _config_text(config)
        else:
            text = "Normal delivery rules" + (" - not charged, because the campaign charge covers the whole order" if g.get("waived") else "")
            if g.get("explanation"):
                text += " \u00b7 " + g["explanation"]
            config = None
            config_text = ""
        groups.append({"label": g.get("label"), "amount": g.get("amount"), "rule_text": text, "config": config, "config_text": config_text,
                       "waived": bool(g.get("waived")), "normal_amount": g.get("normal_amount")})
    note = (order.promotions_applied or {}).get("coupon_excluded_campaign_items") if isinstance(order.promotions_applied, dict) else None
    return {"district": bd.get("district"), "total": bd.get("total"), "groups": groups, "coupon_note": note}


def short_detail_campaign(order):
    rows = campaign_item_rows(order)
    return {
        "has_campaign": bool(rows),
        "campaign_names": sorted({r["campaign_name"] for r in rows if r["campaign_name"]}),
        "campaign_discount_total": float(sum((r["savings_total"] for r in rows), ZERO)),
    }


def delivery_rule_view(order):
    bd = order.delivery_breakdown if isinstance(order.delivery_breakdown, dict) else {}
    normal = next((g for g in (bd.get("groups") or []) if g.get("type") == "normal" and g.get("explanation")), None)
    if not normal:
        return None
    order_wise = normal.get("count_mode") == "ORDER_WISE"
    return {
        "district": bd.get("district"),
        "total": bd.get("total"),
        "mode_text": "Per order (one charge for the whole order)" if order_wise else "Per product (each different product counts once)",
        "source_text": SOURCE_RULE_TEXT.get(normal.get("amount_source"), "") if order_wise else "",
        "explanation": normal.get("explanation"),
        "lines": normal.get("lines") or [],
        "regular_amount": normal.get("amount"),
        "waived": bool(normal.get("waived")),
    }

