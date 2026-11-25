from decimal import Decimal

from pencilwoodbd.choices import (
    CAMPAIGN_DELIVERY_AMOUNT_SOURCE,
    CAMPAIGN_DELIVERY_BASIS,
    CAMPAIGN_DELIVERY_MODE,
    CAMPAIGN_MIXED_CART_DELIVERY,
)
from site_app.bd_districts import BD_DISTRICTS
from site_app.delivery_charge import (
    COUNT_ORDER_WISE, DeliveryChargeResolver, compute_regular_charge, get_delivery_rule,
)

from .pricing import ZERO, num
from site_app.models import SiteDeliveryChargeConfig

NORMAL_GROUP_LABEL = "Regular items"


def is_custom_delivery_line(r):
    return bool(r.applies and r.campaign.delivery_mode == CAMPAIGN_DELIVERY_MODE.CUSTOM)


def has_custom_delivery(results):
    return any(is_custom_delivery_line(r) for r in results)


def _global_config():
    return SiteDeliveryChargeConfig.get_solo().area_and_charge or {}


def regular_group_view(charge, charged=None, waived=False):
    order_wise = charge["count_mode"] == COUNT_ORDER_WISE
    amount = charge["amount"] if charged is None else charged
    if order_wise:
        products = [{"product_id": r["product_id"], "name": r["name"], "resolved_amount": num(r["amount"])}
                    for r in charge["per_product"]]
        lines = [{"label": "Delivery charge (per order)", "amount": num(charge["amount"])}]
    else:
        products = [{"product_id": r["product_id"], "name": r["name"], "amount": num(r["amount"])}
                    for r in charge["per_product"]]
        lines = [{"label": r["name"], "amount": num(r["amount"])} for r in charge["per_product"]]
    return {
        "type": "normal",
        "label": NORMAL_GROUP_LABEL,
        "amount": num(amount),
        "waived": waived,
        "normal_amount": num(charge["amount"]),
        "count_mode": charge["count_mode"],
        "amount_source": charge["amount_source"],
        "explanation": charge["explanation"],
        "lines": lines,
        "products": products,
    }


def _campaign_product_config(campaign, campaign_product):
    if campaign.delivery_amount_source == CAMPAIGN_DELIVERY_AMOUNT_SOURCE.PRODUCT_WISE:
        return campaign_product.delivery_config or campaign.delivery_config
    return campaign.delivery_config


def _for_district(results, district, global_cfg, rule=None):
    normal_products, groups_src = {}, {}
    for r in results:
        if is_custom_delivery_line(r):
            g = groups_src.setdefault(r.campaign.id, {"campaign": r.campaign, "products": {}})
            g["products"].setdefault(r.product.id, (r.product, r.campaign_product))
        else:
            normal_products.setdefault(r.product.id, r.product)

    groups, total = [], ZERO
    for g in groups_src.values():
        campaign = g["campaign"]
        per_product = []
        for product, cp in g["products"].values():
            amount = DeliveryChargeResolver.resolve(
                _campaign_product_config(campaign, cp), district, global_area_and_charge=global_cfg)
            per_product.append((product, amount))
        amounts = [a for _, a in per_product]
        if campaign.delivery_basis == CAMPAIGN_DELIVERY_BASIS.PER_PRODUCT:
            group_amount = sum(amounts, ZERO)
        else:
            group_amount = max(amounts) if amounts else ZERO
        total += group_amount
        groups.append({
            "type": "campaign",
            "campaign_id": campaign.id,
            "campaign_slug": campaign.slug,
            "label": campaign.title,
            "amount": num(group_amount),
            "rule": {
                "delivery_mode": campaign.delivery_mode,
                "amount_source": campaign.delivery_amount_source,
                "basis": campaign.delivery_basis,
                "mixed_cart_delivery": campaign.mixed_cart_delivery,
                "config": campaign.delivery_config,
            },
            "products": [{"product_id": p.id, "name": p.name, "amount": num(a)} for p, a in per_product],
        })

    normal_waived = False
    if normal_products:
        # the regular group: the global counting rule (per product / per order) decides its amount
        charge = compute_regular_charge(normal_products.values(), district, global_map=global_cfg, rule=rule)
        normal_waived = any(
            g["campaign"].mixed_cart_delivery == CAMPAIGN_MIXED_CART_DELIVERY.COMBINED for g in groups_src.values()
        )
        charged = ZERO if normal_waived else charge["amount"]
        total += charged
        groups.append(regular_group_view(charge, charged=charged, waived=normal_waived))
    return total, groups, normal_waived


def compute_delivery(results, district):
    global_cfg = _global_config()
    rule = get_delivery_rule()
    if district:
        total, groups, waived = _for_district(results, district, global_cfg, rule)
        return {
            "total": total,
            "breakdown": _breakdown(district, True, total, groups, waived),
            "range": None,
        }

    per_district = {d: _for_district(results, d, global_cfg, rule) for d in BD_DISTRICTS}
    totals = {d: v[0] for d, v in per_district.items()}
    min_d = min(totals, key=lambda d: (totals[d], d))
    grouped = {}
    for d, t in totals.items():
        grouped.setdefault(t, []).append(d)
    total, groups, waived = per_district[min_d]
    return {
        "total": total,
        "breakdown": _breakdown(min_d, False, total, groups, waived),
        "range": {
            "min": totals[min_d], "max": max(totals.values()), "varies": len(grouped) > 1, "min_district": min_d,
            "groups": [{"charge": c, "districts": sorted(ds)} for c, ds in sorted(grouped.items(), key=lambda kv: kv[0])],
        },
    }


def _breakdown(district, selected, total, groups, normal_waived):
    return {
        "district": district,
        "district_selected": selected,
        "total": num(total),
        "normal_items_waived": normal_waived,
        "count_mode": get_delivery_rule()[0],
        "amount_source": get_delivery_rule()[1],
        "groups": groups,
    }


def plain_breakdown(results, district, total, charge=None):
    if charge is None:
        products = {}
        for r in results:
            products.setdefault(r.product.id, r.product)
        charge = compute_regular_charge(products.values(), district)
    group = regular_group_view(charge, charged=total)
    return {
        "district": district,
        "district_selected": bool(district),
        "total": num(total),
        "normal_items_waived": False,
        "count_mode": charge["count_mode"],
        "amount_source": charge["amount_source"],
        "groups": [group],
    }
