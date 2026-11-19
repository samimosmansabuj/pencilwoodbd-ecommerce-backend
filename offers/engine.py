from django.db.models import Q
from django.utils import timezone

from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, INVENTORY_TYPE, OFFER_GIFT_MODE, OFFER_COUNT_MODE
from product.models import Product, ProductVariant, Category
from .models import Offer, ProductComboPair

BIG = 10 ** 9


class OfferError(Exception):
    pass


def _category_descendants(root_ids):
    if not root_ids:
        return set()
    children = {}
    for cid, pid in Category.objects.values_list("id", "parent_id"):
        children.setdefault(pid, []).append(cid)
    out, stack = set(), list(root_ids)
    while stack:
        cid = stack.pop()
        if cid in out:
            continue
        out.add(cid)
        stack.extend(children.get(cid, []))
    return out


def _running_offers(now=None):
    now = now or timezone.now()
    qs = (
        Offer.objects.filter(is_active=True)
        .filter(Q(start_at__isnull=True) | Q(start_at__lte=now))
        .filter(Q(end_at__isnull=True) | Q(end_at__gte=now))
        .prefetch_related("tiers", "gifts__product__variants__images", "gifts__variant", "gifts__tier",
                          "trigger_products", "trigger_categories")
        .order_by("-priority", "-id")
    )
    return list(qs)


def _qualifier(offer):
    prod_ids = {p.id for p in offer.trigger_products.all()}
    cat_ids = _category_descendants([c.id for c in offer.trigger_categories.all()])

    def qualifies(product):
        if product.is_gift_only:
            return False
        if offer.apply_to_all:
            return True
        return product.id in prod_ids or (product.category_id in cat_ids if product.category_id else False)

    return qualifies


def _active_variants(product):
    """Active variants, default first. Empty list for products without variants."""
    if not product.has_variants:
        return []
    vs = [v for v in product.variants.all() if v.is_active]
    vs.sort(key=lambda v: (not v.is_default, v.id))
    return vs


def _units(obj):
    if obj.inventory_type == INVENTORY_TYPE.UNLIMITED:
        return BIG
    if obj.inventory_type == INVENTORY_TYPE.OUT_OF_STOCK:
        return 0
    return max(obj.inventory_quantity, 0)


def _stock(product, variant):
    if product.status != CATEGORY_PRODUCT_STATUS.ACTIVE:
        return 0
    if variant is not None:
        return _units(variant) if variant.is_active else 0
    if product.has_variants:
        return 0
    return _units(product)


def variant_label(variant):
    attrs = variant.attributes or {}
    return " / ".join(str(v) for v in attrs.values() if str(v).strip()) or f"#{variant.id}"


def _img(product, abs_url):
    url = product.primary_image
    if url and abs_url:
        return abs_url(url)
    return url or ""


def _variant_img(product, variant, abs_url):
    try:
        gallery = product.variant_gallery(variant, _active_variants(product))
    except Exception:
        gallery = []
    for g in gallery:
        if g.image:
            return abs_url(g.image.url) if abs_url else g.image.url
    return _img(product, abs_url)


def _price(obj, product=None):
    return float(obj.discount_price or obj.price or 0) or (float((product.discount_price or product.price) or 0) if product else 0)


def _line_name(product, variant):
    return f"{product.name} ({variant_label(variant)})" if variant else product.name


def evaluate(lines, picks=None, strict=False, abs_url=None, now=None):
    picks = picks if isinstance(picks, dict) else {}
    offers = _running_offers(now)
    if not offers or not lines:
        return {"offers": [], "gift_lines": []}

    products = Product.objects.in_bulk({int(l["product_id"]) for l in lines})
    var_ids = {int(l["variant_id"]) for l in lines if l.get("variant_id")}
    variants = ProductVariant.objects.in_bulk(var_ids) if var_ids else {}

    cart = []
    paid_qty = {}
    for l in lines:
        p = products.get(int(l["product_id"]))
        q = int(l.get("quantity") or 0)
        v = variants.get(int(l["variant_id"])) if l.get("variant_id") else None
        if v is not None and v.product_id != (p.id if p else None):
            v = None
        if p and q > 0:
            cart.append([p, v, q])
            key = (p.id, v.id if v else None)
            paid_qty[key] = paid_qty.get(key, 0) + q

    remaining = [c[2] for c in cart]
    gifted = {}
    gift_lines, ui = [], []

    # combo partners for all pool products
    pool_ids = {g.product_id for o in offers for g in o.gifts.all()}
    partners = {}
    if pool_ids:
        for a, b in ProductComboPair.objects.filter(Q(product_a_id__in=pool_ids) | Q(product_b_id__in=pool_ids)).values_list("product_a_id", "product_b_id"):
            partners.setdefault(a, set()).add(b)
            partners.setdefault(b, set()).add(a)

    def available(product, variant):
        stock = _stock(product, variant)
        if stock >= BIG:
            return BIG
        key = (product.id, variant.id if variant else None)
        return max(stock - paid_qty.get(key, 0) - gifted.get(key, 0), 0)

    def default_variant(product):
        vs = _active_variants(product)
        if not vs:
            return None, (available(product, None) > 0)
        for v in vs:
            if available(product, v) > 0:
                return v, True
        return vs[0], False

    def add_gift_line(product, variant, qty, offer, tier):
        key = (product.id, variant.id if variant else None)
        gifted[key] = gifted.get(key, 0) + qty
        for gl in gift_lines:
            if gl["product"].id == product.id and gl["offer"].id == offer.id and \
                    (gl["variant"].id if gl["variant"] else None) == key[1] and gl["tier"].id == tier.id:
                gl["quantity"] += qty
                return
        gift_lines.append({"product": product, "variant": variant, "quantity": qty, "offer": offer, "tier": tier})

    for offer in offers:
        qualifies = _qualifier(offer)
        tiers = list(offer.tiers.all())
        if not tiers:
            continue

        groups = {}
        for i, (p, v, _) in enumerate(cart):
            if remaining[i] <= 0 or not qualifies(p):
                continue
            if offer.count_mode == OFFER_COUNT_MODE.VARIANT:
                key = (p.id, v.id if v else None)
            elif offer.count_mode == OFFER_COUNT_MODE.PRODUCT:
                key = (p.id,)
            else:
                key = ("all",)
            groups.setdefault(key, []).append(i)

        def group_qty(idxs):
            return sum(remaining[i] for i in idxs)

        def group_name(idxs):
            p, v, _ = cart[idxs[0]]
            if offer.count_mode == OFFER_COUNT_MODE.ALL:
                return ""
            return _line_name(p, v) if offer.count_mode == OFFER_COUNT_MODE.VARIANT else p.name

        total_qual = sum(group_qty(ix) for ix in groups.values())
        best = max(groups.values(), key=group_qty) if groups else []
        best_qty = group_qty(best) if best else 0

        entry = {
            "id": offer.id, "name": offer.name, "description": offer.description,
            "mode": offer.gift_mode, "count_mode": offer.count_mode,
            "qualifying_qty": best_qty if offer.count_mode != OFFER_COUNT_MODE.ALL else total_qual,
            "tiers": [{"buy_qty": t.buy_qty, "free_qty": t.free_qty} for t in tiers],
            "matched_tier": None, "next_tier": None, "earned_free": 0,
            "require_selection": offer.require_selection,
            "selected_count": 0, "remaining": 0, "picks": [], "pool": [], "auto_gifts": [], "notes": [],
            "groups": [],
            "link": None,
        }
        link_idx = (best or next(iter(groups.values()), [None]))[0] if groups else None
        if link_idx is not None:
            entry["link"] = {"product_id": cart[link_idx][0].id, "slug": cart[link_idx][0].slug}

        nudge_src = None
        for idxs in groups.values():
            q = group_qty(idxs)
            nxt = next((t for t in tiers if t.buy_qty > q), None)
            if nxt and q > 0 and (nudge_src is None or q > nudge_src[0]):
                nudge_src = (q, nxt, idxs)
        if nudge_src:
            q, nxt, idxs = nudge_src
            entry["next_tier"] = {"buy_qty": nxt.buy_qty, "free_qty": nxt.free_qty, "need_more": nxt.buy_qty - q,
                                  "group": group_name(idxs)}

        results = []
        for idxs in groups.values():
            q = group_qty(idxs)
            matched = None
            for t in tiers:
                if t.buy_qty <= q:
                    matched = t
            if not matched:
                continue
            mult = (q // matched.buy_qty) if offer.repeat else 1
            need = matched.buy_qty * mult if offer.repeat else q
            name = group_name(idxs)
            for i in idxs:
                take = min(remaining[i], need)
                remaining[i] -= take
                need -= take
                if need <= 0:
                    break
            results.append((idxs, matched, mult, name, q))
            entry["groups"].append({"name": name, "qty": q, "buy_qty": matched.buy_qty, "times": mult})

        if not results:
            if total_qual > 0:
                ui.append(entry)
            continue

        top = max((r[1] for r in results), key=lambda t: t.buy_qty)
        entry["matched_tier"] = {"buy_qty": top.buy_qty, "free_qty": top.free_qty}
        cap = offer.max_free_per_order if offer.max_free_per_order else BIG

        # ---------------- AUTO mode ----------------
        if offer.gift_mode == OFFER_GIFT_MODE.AUTO:
            for idxs, matched, mult, name, _q in results:
                for g in offer.gifts.all():
                    if g.tier_id and g.tier_id != matched.id:
                        continue
                    want = min(g.quantity * mult, cap)
                    if want <= 0:
                        continue
                    if g.variant_id:
                        variant = g.variant if (g.variant and g.variant.is_active) else None
                        ok = variant is not None and available(g.product, variant) > 0
                    else:
                        variant, ok = default_variant(g.product)
                    if not ok:
                        entry["notes"].append(f"{_line_name(g.product, variant)} out of stock")
                        continue
                    qty = min(want, available(g.product, variant))
                    if qty <= 0:
                        continue
                    cap -= qty
                    add_gift_line(g.product, variant, qty, offer, matched)
            for gl in gift_lines:
                if gl["offer"].id == offer.id:
                    entry["auto_gifts"].append({
                        "product_id": gl["product"].id, "variant_id": gl["variant"].id if gl["variant"] else None,
                        "name": _line_name(gl["product"], gl["variant"]), "quantity": gl["quantity"],
                        "image": _variant_img(gl["product"], gl["variant"], abs_url) if gl["variant"] else _img(gl["product"], abs_url),
                    })
            entry["earned_free"] = sum(a["quantity"] for a in entry["auto_gifts"])
            ui.append(entry)
            continue

        # ---------------- CHOOSE mode ----------------
        earned = min(sum(r[1].free_qty * r[2] for r in results), cap)
        entry["earned_free"] = earned
        pool = {}
        for g in offer.gifts.all():
            pool.setdefault(g.product_id, g.product)

        tier_for_lines = top

        raw = picks.get(str(offer.id)) or picks.get(offer.id) or []
        chosen, total = {}, 0
        for r in raw if isinstance(raw, list) else []:
            try:
                pid, q = int(r.get("product_id")), int(r.get("quantity") or 1)
                vid = int(r["variant_id"]) if r.get("variant_id") not in (None, "", 0, "0") else None
            except (TypeError, ValueError, AttributeError):
                continue
            if q <= 0:
                continue
            if pid not in pool:
                if strict:
                    raise OfferError("This free item is not part of the offer")
                continue
            product = pool[pid]
            variant = None
            vs = _active_variants(product)
            if vs:
                variant = next((v for v in vs if v.id == vid), None)
                if variant is None:
                    if strict:
                        raise OfferError(f"Please choose a variant for {product.name}")
                    continue
            if total + q > earned:
                if strict:
                    raise OfferError(f"'{offer.name}': you can take at most {earned} free item(s)")
                q = earned - total
                if q <= 0:
                    continue
            key = (pid, variant.id if variant else None)
            have = available(product, variant) - chosen.get(key, 0)
            if have < q:
                if strict:
                    raise OfferError(f"{_line_name(product, variant)} is out of stock, please choose another")
                q = max(have, 0)
                if q <= 0:
                    continue
            chosen[key] = chosen.get(key, 0) + q
            total += q

        for (pid, vid), q in chosen.items():
            product = pool[pid]
            variant = next((v for v in _active_variants(product) if v.id == vid), None) if vid else None
            add_gift_line(product, variant, q, offer, tier_for_lines)

        entry["picks"] = [{"product_id": pid, "variant_id": vid, "quantity": q} for (pid, vid), q in chosen.items()]
        entry["selected_count"] = total
        entry["remaining"] = max(earned - total, 0)

        capacity = 0
        for pid, product in pool.items():
            vs = _active_variants(product)
            options = []
            if vs:
                for v in vs:
                    avail = available(product, v) + chosen.get((pid, v.id), 0)
                    options.append({
                        "variant_id": v.id, "label": variant_label(v), "attributes": v.attributes or {},
                        "image": _variant_img(product, v, abs_url), "price": _price(v, product),
                        "available": avail >= 1, "max_pick": earned if avail >= BIG else min(avail, earned),
                    })
                    capacity += min(avail, earned)
                p_avail = any(o["available"] for o in options)
                p_max = max((o["max_pick"] for o in options), default=0)
            else:
                avail = available(product, None) + chosen.get((pid, None), 0)
                capacity += min(avail, earned)
                p_avail = avail >= 1
                p_max = earned if avail >= BIG else min(avail, earned)
            entry["pool"].append({
                "product_id": pid, "name": product.name, "slug": product.slug,
                "image": _img(product, abs_url), "price": _price(product),
                "has_variants": bool(vs), "variants": options,
                "available": p_avail, "max_pick": p_max,
                "combo_with": sorted(partners.get(pid, [])),
            })
        if strict and offer.require_selection and total < earned and capacity > total:
            raise OfferError(f"'{offer.name}': please choose your free item(s) ({earned - total} left)")
        ui.append(entry)

    return {"offers": ui, "gift_lines": gift_lines}


def offers_for_product(product, abs_url=None):
    out = []
    if product.is_gift_only:
        return out
    for offer in _running_offers():
        if not _qualifier(offer)(product):
            continue
        tiers = list(offer.tiers.all())
        if not tiers:
            continue
        pool = []
        for g in offer.gifts.all():
            if g.product.status == CATEGORY_PRODUCT_STATUS.ACTIVE:
                pool.append({"product_id": g.product_id, "name": g.product.name, "image": _img(g.product, abs_url),
                             "quantity": g.quantity, "variant_count": len(_active_variants(g.product))})
        out.append({
            "id": offer.id, "name": offer.name, "description": offer.description, "mode": offer.gift_mode,
            "count_mode": offer.count_mode, "repeat": offer.repeat,
            "tiers": [{"buy_qty": t.buy_qty, "free_qty": t.free_qty} for t in tiers],
            "gifts": pool[:12],
            "end_at": offer.end_at.isoformat() if offer.end_at else None,
        })
    return out
