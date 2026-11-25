# site_app/delivery_charge.py
"""
Single reusable class for resolving a delivery charge.

Usage (anywhere in the codebase — cart, order creation, invoice,
storefront product page, admin dashboard, API serializer, etc.):

    from site_app.delivery_charge import DeliveryChargeResolver

    charge = DeliveryChargeResolver.get_charge(product, district="Dhaka")
    # -> Decimal

    # If you already have the JSON dicts loaded (avoids extra DB hits when
    # resolving for many order items against the same product):
    charge = DeliveryChargeResolver.resolve(
        product_area_and_charge=product.delivery_charge.area_and_charge if hasattr(product, "delivery_charge") else None,
        district="Dhaka",
    )

Resolution order (first match wins):
    1. Product-specific charge for this exact district
    2. Product-specific "all" bulk charge
    3. Global config charge for this exact district
    4. Global config "all" bulk charge
    5. SYSTEM_DEFAULT_DELIVERY_CHARGE (hardcoded fallback, e.g. 100)
"""
from decimal import Decimal, InvalidOperation

from site_app.bd_districts import ALL_DISTRICTS_KEY, SYSTEM_DEFAULT_DELIVERY_CHARGE


class DeliveryChargeResolver:

    @staticmethod
    def _safe_decimal(value):
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @classmethod
    def _lookup(cls, area_and_charge, district):
        """Look inside ONE scope's JSON dict for a district or 'all' match."""
        if not area_and_charge or not isinstance(area_and_charge, dict):
            return None

        if district:
            # Case-sensitive first (fast path), then a forgiving case-insensitive retry
            if district in area_and_charge:
                value = cls._safe_decimal(area_and_charge.get(district))
                if value is not None:
                    return value
            else:
                for key, val in area_and_charge.items():
                    if key.lower() == district.lower():
                        value = cls._safe_decimal(val)
                        if value is not None:
                            return value

        # Fall back to the "all" bulk value within this same scope
        value = cls._safe_decimal(area_and_charge.get(ALL_DISTRICTS_KEY))
        if value is not None:
            return value

        return None

    @classmethod
    def resolve(cls, product_area_and_charge, district, global_area_and_charge=None):
        """
        Pure function version — pass in already-fetched JSON dicts.
        Use this when you're resolving charges for many order items and
        don't want to re-query the global config / product relation each time.
        """
        # 1 & 2: product-specific (district, then its own "all")
        result = cls._lookup(product_area_and_charge, district)
        if result is not None:
            return result

        # 3 & 4: global config (district, then its own "all")
        if global_area_and_charge is None:
            global_area_and_charge = cls._get_global_area_and_charge()
        result = cls._lookup(global_area_and_charge, district)
        if result is not None:
            return result

        # 5: hardcoded system default
        return Decimal(str(SYSTEM_DEFAULT_DELIVERY_CHARGE))

    @classmethod
    def _get_global_area_and_charge(cls):
        from site_app.models import SiteDeliveryChargeConfig
        config = SiteDeliveryChargeConfig.get_solo()
        return config.area_and_charge or {}

    @classmethod
    def get_charge(cls, product, district):
        """
        Convenience entrypoint: pass a Product instance + district string.
        Fetches product.delivery_charge (OneToOne, may not exist) itself.
        """
        product_area_and_charge = None
        delivery_charge_obj = getattr(product, "delivery_charge", None)
        if delivery_charge_obj is not None:
            product_area_and_charge = delivery_charge_obj.area_and_charge

        return cls.resolve(
            product_area_and_charge=product_area_and_charge,
            district=district,
        )

    @classmethod
    def get_breakdown_for_display(cls, product):
        """
        Returns a dict describing, per BD district, what charge would apply
        and which scope it came from — useful for a dashboard "preview" table.
        e.g. {"Dhaka": {"charge": 80, "source": "product"}, ...}
        """
        from site_app.bd_districts import BD_DISTRICTS

        product_area_and_charge = None
        delivery_charge_obj = getattr(product, "delivery_charge", None)
        if delivery_charge_obj is not None:
            product_area_and_charge = delivery_charge_obj.area_and_charge or {}
        else:
            product_area_and_charge = {}

        global_area_and_charge = cls._get_global_area_and_charge()

        breakdown = {}
        for district in BD_DISTRICTS:
            if district in product_area_and_charge:
                breakdown[district] = {"charge": cls._safe_decimal(product_area_and_charge[district]), "source": "product"}
            elif ALL_DISTRICTS_KEY in product_area_and_charge:
                breakdown[district] = {"charge": cls._safe_decimal(product_area_and_charge[ALL_DISTRICTS_KEY]), "source": "product_all"}
            elif district in global_area_and_charge:
                breakdown[district] = {"charge": cls._safe_decimal(global_area_and_charge[district]), "source": "global"}
            elif ALL_DISTRICTS_KEY in global_area_and_charge:
                breakdown[district] = {"charge": cls._safe_decimal(global_area_and_charge[ALL_DISTRICTS_KEY]), "source": "global_all"}
            else:
                breakdown[district] = {"charge": Decimal(str(SYSTEM_DEFAULT_DELIVERY_CHARGE)), "source": "system_default"}
        return breakdown

    @classmethod
    def cart_range(cls, products, config=None):
        """
        Estimate before a district is chosen: the order charge of every district, using the global
        counting rule (compute_regular_charge). PRODUCT_WISE: sum of the distinct products. ORDER_WISE:
        the single order charge. "per_product_at_min" always holds the RESOLVED amount of each product
        at the cheapest district (reference data; in ORDER_WISE it is not what the customer pays).
        """
        from site_app.bd_districts import BD_DISTRICTS

        products = _distinct_products(products)
        config = config or _get_config()
        rule = get_delivery_rule(config)
        global_map = (config.area_and_charge or {}) if config is not None else cls._get_global_area_and_charge()

        totals, details = {}, {}
        for d in BD_DISTRICTS:
            res = compute_regular_charge(products, d, global_map=global_map, rule=rule)
            details[d] = res["per_product_amounts"]
            totals[d] = res["amount"]

        if not totals:
            return None
        min_d = min(totals, key=lambda k: (totals[k], k))
        grouped = {}
        for d, t in totals.items():
            grouped.setdefault(t, []).append(d)
        groups = [{"charge": c, "districts": sorted(ds)} for c, ds in sorted(grouped.items(), key=lambda kv: kv[0])]
        return {
            "min": totals[min_d], "max": max(totals.values()), "varies": len(grouped) > 1,
            "min_district": min_d, "per_product_at_min": details[min_d], "groups": groups,
            "count_mode": rule[0], "order_wise_amount_source": rule[1],
        }



COUNT_PRODUCT_WISE = "PRODUCT_WISE"
COUNT_ORDER_WISE = "ORDER_WISE"
SOURCE_GLOBAL = "GLOBAL"
SOURCE_LOWEST = "LOWEST"
SOURCE_HIGHEST = "HIGHEST"
_VALID_MODES = (COUNT_PRODUCT_WISE, COUNT_ORDER_WISE)
_VALID_SOURCES = (SOURCE_GLOBAL, SOURCE_LOWEST, SOURCE_HIGHEST)


def _get_config():
    from site_app.models import SiteDeliveryChargeConfig
    return SiteDeliveryChargeConfig.get_solo()


def get_delivery_rule(config=None):
    if config is None:
        config = _get_config()
    mode = getattr(config, "count_mode", None)
    source = getattr(config, "order_wise_amount_source", None)
    return (mode if mode in _VALID_MODES else COUNT_PRODUCT_WISE,
            source if source in _VALID_SOURCES else SOURCE_GLOBAL)


def _distinct_products(products):
    seen, out = set(), []
    for p in products or []:
        if p is None or p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def _money(amount):
    amount = Decimal(str(amount))
    return f"\u09F3{int(amount)}" if amount == amount.to_integral_value() else f"\u09F3{amount.quantize(Decimal('0.01'))}"


def compute_regular_charge(products, district, config=None, global_map=None, rule=None):

    products = _distinct_products(products)
    if rule is None:
        rule = get_delivery_rule(config)
    mode, source = rule
    if global_map is None:
        global_map = (config.area_and_charge or {}) if config is not None else DeliveryChargeResolver._get_global_area_and_charge()

    per_product, amounts = [], {}
    for p in products:
        obj = getattr(p, "delivery_charge", None)
        product_map = obj.area_and_charge if obj is not None else None
        amount = DeliveryChargeResolver.resolve(product_map, district, global_area_and_charge=global_map)
        amounts[p.id] = amount
        per_product.append({"product_id": p.id, "name": p.name, "amount": amount})

    global_amount = DeliveryChargeResolver.resolve(None, district, global_area_and_charge=global_map)
    values = [row["amount"] for row in per_product]
    listing = " + ".join(f"{row['name']} {_money(row['amount'])}" for row in per_product)

    if not values:
        total, explanation = Decimal("0"), "No regular products, so no regular delivery charge."
    elif mode == COUNT_PRODUCT_WISE:
        total = sum(values, Decimal("0"))
        explanation = (f"Per product: {listing} = {_money(total)}. "
                       "Variants and quantity of the same product count once.")
    elif source == SOURCE_LOWEST:
        total = min(values)
        explanation = f"Per order, lowest product charge: {listing} \u2192 {_money(total)} for the whole order."
    elif source == SOURCE_HIGHEST:
        total = max(values)
        explanation = f"Per order, highest product charge: {listing} \u2192 {_money(total)} for the whole order."
    else:
        total = global_amount
        explanation = (f"Per order, global charge: {_money(total)} for the whole order "
                       "(product-wise charges are ignored).")

    return {
        "amount": total, "count_mode": mode, "amount_source": source,
        "per_product": per_product, "per_product_amounts": amounts,
        "global_amount": global_amount, "explanation": explanation,
    }


def line_delivery_charges(product_ids, result):

    seen, out = set(), []
    for pid in product_ids:
        if pid is None or result["count_mode"] == COUNT_ORDER_WISE or pid in seen:
            out.append(Decimal("0"))
            continue
        seen.add(pid)
        out.append(result["per_product_amounts"].get(pid, Decimal("0")))
    return out


def single_product_charge(product, district, config=None):
    return compute_regular_charge([product], district, config=config)["amount"]


def delivery_info_rule(config=None):
    mode, source = get_delivery_rule(config)
    return {"count_mode": mode, "order_wise_amount_source": source}

