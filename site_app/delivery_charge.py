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
    def cart_range(cls, products):
        from site_app.bd_districts import BD_DISTRICTS

        global_map = cls._get_global_area_and_charge()
        per_product_maps = {}
        for p in products:
            obj = getattr(p, "delivery_charge", None)
            per_product_maps[p.id] = (obj.area_and_charge if obj is not None else None)

        totals, details = {}, {}
        for d in BD_DISTRICTS:
            row = {pid: cls.resolve(m, d, global_area_and_charge=global_map) for pid, m in per_product_maps.items()}
            details[d] = row
            totals[d] = sum(row.values(), Decimal("0"))

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
        }
