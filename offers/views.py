import json
from http import HTTPStatus

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views import View

from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, OFFER_GIFT_MODE, OFFER_COUNT_MODE
from product.models import Product, ProductVariant, Category
from .models import Offer, OfferTier, OfferGift, ProductComboPair


def _bad(msg):
    return JsonResponse({"status": False, "message": msg}, status=HTTPStatus.BAD_REQUEST)


def _dt(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M") if dt else ""


def _image_map(product_ids=None):
    from product.models import ProductImage
    from pencilwoodbd.choices import PRODUCT_MEDIA_ROLE
    qs = ProductImage.objects.filter(variant__isnull=True).exclude(image="").order_by("position", "id")
    if product_ids is not None:
        qs = qs.filter(product_id__in=product_ids)
    out = {}
    for pid, img, role in qs.values_list("product_id", "image", "role"):
        if pid not in out or role == PRODUCT_MEDIA_ROLE.PRIMARY:
            out[pid] = img
    from django.conf import settings
    base = settings.MEDIA_URL or "/media/"
    return {pid: base + str(img).lstrip("/") for pid, img in out.items()}


def _parse_int(value, default):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return default


def offer_status(o, now=None):
    now = now or timezone.now()
    if not o.is_active:
        return "inactive"
    if o.start_at and o.start_at > now:
        return "scheduled"
    if o.end_at and o.end_at < now:
        return "ended"
    return "running"


def _status_q(status, now):
    running = Q(is_active=True) & (Q(start_at__isnull=True) | Q(start_at__lte=now)) & (Q(end_at__isnull=True) | Q(end_at__gte=now))
    return {
        "running": running,
        "scheduled": Q(is_active=True, start_at__gt=now),
        "ended": Q(is_active=True, end_at__lt=now),
        "inactive": Q(is_active=False),
    }.get(status)


def _variant_label(v):
    attrs = v.attributes or {}
    return " / ".join(str(x) for x in attrs.values() if str(x).strip()) or f"#{v.id}"


class OfferListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        now = timezone.now()
        search = request.GET.get("q", "").strip()
        status = request.GET.get("status", "all")
        per_page = _parse_int(request.GET.get("per_page"), 10)

        base = Offer.objects.all()
        counts = {"all": base.count()}
        for key in ("running", "scheduled", "ended", "inactive"):
            counts[key] = base.filter(_status_q(key, now)).count()

        qs = base.prefetch_related("tiers", "gifts__product", "gifts__variant", "trigger_products", "trigger_categories")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if _status_q(status, now) is not None:
            qs = qs.filter(_status_q(status, now))
        qs = qs.order_by("-id")

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        images = _image_map()
        rows = []
        for o in page_obj:
            tprods = list(o.trigger_products.all())
            rows.append({
                "o": o,
                "status": offer_status(o, now),
                "products": [{"name": p.name, "image": images.get(p.id, "")} for p in tprods[:3]],
                "products_more": max(len(tprods) - 3, 0),
                "categories": [c.name for c in o.trigger_categories.all()],
                "tiers": [{"buy": t.buy_qty, "free": t.free_qty} for t in o.tiers.all()],
                "gifts": [{
                    "name": g.product.name, "image": images.get(g.product_id, ""), "quantity": g.quantity,
                    "variant": _variant_label(g.variant) if g.variant else "",
                } for g in o.gifts.all()][:4],
                "gifts_more": max(o.gifts.count() - 4, 0),
            })

        context = {
            "rows": rows, "offers": page_obj, "page_obj": page_obj, "paginator": paginator,
            "offer_counts": counts, "current_status": status, "current_search": search,
            "current_per_page": str(per_page),
            "status_tabs": [("all", "All"), ("running", "Running"), ("scheduled", "Scheduled"),
                            ("ended", "Ended"), ("inactive", "Inactive")],
        }
        if request.htmx and request.headers.get("HX-Target") == "offer-table-wrapper":
            return render(request, "db_offers/partial/partial_offer_list.html", context)

        context.update(_editor_data())
        return render(request, "db_offers/offer_list.html", context)


def _editor_data():
    images = _image_map()
    products = list(
        Product.objects.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE)
        .order_by("name").values("id", "name", "price", "discount_price", "is_gift_only")
    )
    variants = {}
    for v in ProductVariant.objects.filter(is_active=True, product__status=CATEGORY_PRODUCT_STATUS.ACTIVE).order_by("-is_default", "id"):
        variants.setdefault(v.product_id, []).append({"id": v.id, "label": _variant_label(v), "stock": v.available_stock if v.inventory_type != "unlimited" else None})
    catalog = [{
        "id": p["id"], "name": p["name"], "image": images.get(p["id"], ""),
        "price": float(p["discount_price"] or p["price"] or 0), "gift_only": p["is_gift_only"],
        "variants": variants.get(p["id"], []),
    } for p in products]
    return {
        "catalog": catalog,
        "categories_data": [{"id": c.id, "name": c.name} for c in Category.objects.order_by("name")],
    }


def _offer_json(o):
    return {
        "id": o.id, "name": o.name, "description": o.description, "is_active": o.is_active,
        "start_at": _local(o.start_at), "end_at": _local(o.end_at),
        "priority": o.priority, "gift_mode": o.gift_mode, "count_mode": o.count_mode,
        "require_selection": o.require_selection, "repeat": o.repeat,
        "max_free_per_order": o.max_free_per_order or "", "apply_to_all": o.apply_to_all,
        "products": [p.id for p in o.trigger_products.all()],
        "categories": [c.id for c in o.trigger_categories.all()],
        "tiers": [{"id": t.id, "buy_qty": t.buy_qty, "free_qty": t.free_qty} for t in o.tiers.all()],
        "gifts": [{
            "product": g.product_id, "variant": g.variant_id, "tier": g.tier.buy_qty if g.tier_id else "",
            "quantity": g.quantity,
        } for g in o.gifts.all()],
    }


class OfferDataView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, pk):
        o = get_object_or_404(
            Offer.objects.prefetch_related("tiers", "gifts__tier", "trigger_products", "trigger_categories"), pk=pk)
        return JsonResponse({"status": True, "offer": _offer_json(o)})


class OfferSaveView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        try:
            d = json.loads(request.body or "{}")
        except ValueError:
            return _bad("Invalid data")

        name = (d.get("name") or "").strip()
        if not name:
            return _bad("Offer name is required")
        mode = d.get("gift_mode") if d.get("gift_mode") in (OFFER_GIFT_MODE.CHOOSE, OFFER_GIFT_MODE.AUTO) else OFFER_GIFT_MODE.CHOOSE
        count_mode = d.get("count_mode") if d.get("count_mode") in (OFFER_COUNT_MODE.ALL, OFFER_COUNT_MODE.PRODUCT, OFFER_COUNT_MODE.VARIANT) else OFFER_COUNT_MODE.ALL

        try:
            product_ids = [int(x) for x in d.get("products") or []]
            category_ids = [int(x) for x in d.get("categories") or []]
        except (TypeError, ValueError):
            return _bad("Invalid product or category")
        apply_to_all = bool(d.get("apply_to_all"))
        if not (apply_to_all or product_ids or category_ids):
            return _bad("Choose the products or categories this offer applies to")

        tiers, seen = [], set()
        for t in d.get("tiers") or []:
            try:
                b, f = int(t.get("buy_qty")), int(t.get("free_qty") or 0)
            except (TypeError, ValueError):
                return _bad("Buy / free quantity is not valid")
            if b < 1 or (mode == OFFER_GIFT_MODE.CHOOSE and f < 1):
                return _bad("Buy and free quantity must both be 1 or more")
            if b in seen:
                return _bad(f"'Buy {b}' is added twice")
            seen.add(b)
            tiers.append({"buy_qty": b, "free_qty": max(f, 1)})
        if not tiers:
            return _bad("Add at least one rule (for example: buy 2, get 1 free)")

        gifts = d.get("gifts") or []
        if not gifts:
            return _bad("Add at least one free product")

        with transaction.atomic():
            offer = get_object_or_404(Offer, id=d["id"]) if d.get("id") else Offer()
            offer.name = name[:150]
            offer.description = (d.get("description") or "").strip()[:255]
            offer.is_active = bool(d.get("is_active", True))
            offer.start_at = _dt(d.get("start_at"))
            offer.end_at = _dt(d.get("end_at"))
            if offer.start_at and offer.end_at and offer.end_at <= offer.start_at:
                return _bad("End time must be after the start time")
            offer.priority = int(d.get("priority") or 0)
            offer.gift_mode = mode
            offer.count_mode = count_mode
            offer.require_selection = bool(d.get("require_selection", True))
            offer.repeat = bool(d.get("repeat"))
            offer.max_free_per_order = int(d["max_free_per_order"]) if d.get("max_free_per_order") else None
            offer.apply_to_all = apply_to_all
            offer.save()
            offer.trigger_products.set(product_ids)
            offer.trigger_categories.set(category_ids)

            # tiers: keep ids stable where buy_qty is unchanged
            existing = {t.buy_qty: t for t in offer.tiers.all()}
            keep, tier_by_buy = set(), {}
            for t in tiers:
                obj = existing.get(t["buy_qty"]) or OfferTier(offer=offer, buy_qty=t["buy_qty"])
                obj.free_qty = t["free_qty"]
                obj.save()
                keep.add(obj.id)
                tier_by_buy[t["buy_qty"]] = obj
            offer.tiers.exclude(id__in=keep).delete()

            offer.gifts.all().delete()
            made = 0
            for pos, g in enumerate(gifts):
                try:
                    pid = int(g.get("product"))
                except (TypeError, ValueError):
                    continue
                variant = None
                if mode == OFFER_GIFT_MODE.AUTO and g.get("variant"):
                    variant = ProductVariant.objects.filter(id=g["variant"], product_id=pid).first()
                    if variant is None:
                        transaction.set_rollback(True)
                        return _bad("The chosen variant does not belong to that product")
                tier_obj = None
                tier_key = g.get("tier") or g.get("tier_buy")
                if mode == OFFER_GIFT_MODE.AUTO and tier_key:
                    tier_obj = tier_by_buy.get(int(tier_key))
                OfferGift.objects.create(
                    offer=offer, product_id=pid, variant=variant, tier=tier_obj,
                    quantity=max(int(g.get("quantity") or 1), 1), position=pos,
                )
                made += 1
            if not made:
                transaction.set_rollback(True)
                return _bad("Add at least one free product")
        return JsonResponse({"status": True, "message": "Offer saved", "id": offer.id})


class OfferToggleView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        offer.is_active = not offer.is_active
        offer.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"status": True, "is_active": offer.is_active})


class OfferDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        get_object_or_404(Offer, pk=pk).delete()
        return JsonResponse({"status": True, "message": "Offer deleted"})


class ComboAddView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        try:
            d = json.loads(request.body or "{}")
            a, b = int(d.get("product_a")), int(d.get("product_b"))
        except (TypeError, ValueError):
            return _bad("দুটি প্রোডাক্ট বেছে নিন")
        if a == b:
            return _bad("একই প্রোডাক্ট দুইবার দেওয়া যাবে না")
        if ProductComboPair.objects.filter(product_a_id__in=(a, b), product_b_id__in=(a, b)).exists():
            return _bad("এই জোড়া আগেই আছে")
        ProductComboPair.objects.create(product_a_id=a, product_b_id=b)
        return JsonResponse({"status": True, "message": "কম্বো জোড়া যোগ হয়েছে"})


class ComboDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        get_object_or_404(ProductComboPair, pk=pk).delete()
        return JsonResponse({"status": True})
