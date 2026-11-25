import io
import json
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from pencilwoodbd.choices import (
    CAMPAIGN_BADGE_MODE,
    CAMPAIGN_DELIVERY_AMOUNT_SOURCE,
    CAMPAIGN_DELIVERY_BASIS,
    CAMPAIGN_DELIVERY_MODE,
    CAMPAIGN_DISCOUNT_TYPE,
    CAMPAIGN_MIXED_CART_DELIVERY,
    CAMPAIGN_PRICE_SOURCE,
    CAMPAIGN_STATUS,
    CAMPAIGN_SURFACE,
    CAMPAIGN_SWITCH_MODE,
    CAMPAIGN_VARIANT_MODE,
    CATEGORY_PRODUCT_STATUS,
    PRODUCT_MEDIA_ROLE,
)
from product.models import Product, ProductImage

from .models import (
    BADGE_LABEL_MAX_LENGTH,
    Campaign,
    CampaignProduct,
    CampaignProductVariant,
    _unique_campaign_slug,
    validate_delivery_config,
    validate_discount,
)
from .pricing import (
    active_variants,
    find_overlap_conflicts,
    get_campaign_status,
    num,
    resolve_line_price,
)
from offers.engine import _qualifier, _running_offers
from PIL import Image

IMAGE_FIELDS = ("thumbnail", "banner_desktop", "banner_mobile")
IMAGE_MAX_WIDTH = {"thumbnail": 800, "banner_desktop": 2000, "banner_mobile": 1200}
IMAGE_MAX_BYTES = 8 * 1024 * 1024

WARNING_TEXT = {
    "no_visible_discount": "the campaign price is not lower than the struck-through price (no discount is shown)",
    "above_current_price": "customers would pay MORE than the product's current price",
    "variant_discount_missing": "a variant has no campaign discount (it keeps the normal price)",
    "invalid_discount_value": "the discount value is not valid",
    "no_active_variant": "the product has no active variant",
}


def status_q(status, now=None):
    now = now or timezone.now()
    return {
        CAMPAIGN_STATUS.DRAFT: Q(is_active=False),
        CAMPAIGN_STATUS.UPCOMING: Q(is_active=True, start_at__gt=now),
        CAMPAIGN_STATUS.LIVE: Q(is_active=True, start_at__lte=now, end_at__gte=now),
        CAMPAIGN_STATUS.ENDED: Q(is_active=True, end_at__lt=now),
    }.get(status)


def local_str(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M") if dt else ""


def parse_local_dt(value):
    if not value:
        return None
    dt = parse_datetime(str(value).strip())
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _image_urls(product_ids):
    qs = ProductImage.objects.filter(product_id__in=product_ids, variant__isnull=True).exclude(image="").order_by("position", "id")
    out = {}
    base = settings.MEDIA_URL or "/media/"
    for pid, img, role in qs.values_list("product_id", "image", "role"):
        if pid not in out or role == PRODUCT_MEDIA_ROLE.PRIMARY:
            out[pid] = base + str(img).lstrip("/")
    return out


def _variant_label(v):
    attrs = v.attributes or {}
    return " / ".join(str(x) for x in attrs.values() if str(x).strip()) or f"#{v.id}"


def product_cards(products, now=None):

    products = list(products)
    images = _image_urls([p.id for p in products])
    qualifiers = [(o.name, _qualifier(o)) for o in _running_offers(now)]
    cards = []
    for p in products:
        variants = [
            {"id": v.id, "label": _variant_label(v), "sku": v.sku or "",
             "price": num(v.price), "discount_price": num(v.discount_price)}
            for v in active_variants(p)
        ]
        display = p.display_variant if p.has_variants else None
        cards.append({
            "id": p.id,
            "name": p.name,
            "sku": p.sku or "",
            "category": p.category.name if p.category_id else "",
            "image": images.get(p.id, ""),
            "price": num(p.price),
            "discount_price": num(p.discount_price),
            "has_variants": bool(variants),
            "display_variant_id": display.id if display is not None else None,
            "variants": variants,
            "has_gift": bool(list(p.gift_product.all())),
            "offers": [name for name, qualifies in qualifiers if qualifies(p)],
        })
    return cards


def product_search_queryset(query, exclude_ids=()):
    qs = (
        Product.objects.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE, is_gift_only=False)
        .select_related("category")
        .prefetch_related("variants", "gift_product")
    )
    if exclude_ids:
        qs = qs.exclude(id__in=list(exclude_ids))
    query = (query or "").strip()
    if query:
        cond = (Q(name__icontains=query) | Q(sku__icontains=query) | Q(category__name__icontains=query)
                | Q(variants__sku__icontains=query))
        if query.isdigit():
            cond |= Q(id=int(query))
        qs = qs.filter(cond).distinct()
    return qs.order_by("name")


def _row_data(cp):
    return {
        "discount_type": cp.discount_type,
        "discount_value": num(cp.discount_value) if cp.discount_value else "",
        "variant_mode": cp.variant_mode,
        "stock_limit": cp.stock_limit if cp.stock_limit is not None else "",
        "gift_mode": cp.gift_mode,
        "offer_mode": cp.offer_mode,
        "discount_base": cp.discount_base_override,
        "strike_price_display": cp.strike_price_override,
        "delivery_config": cp.delivery_config or {},
        "variants": {
            str(vd.variant_id): {"discount_type": vd.discount_type, "discount_value": num(vd.discount_value)}
            for vd in cp.variant_discounts.all()
        },
    }


def campaign_form_data(campaign=None):
    now = timezone.now()
    if campaign is None:
        start = (timezone.localtime(now) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        campaign = Campaign(
            title="", start_at=start, end_at=start + timedelta(days=3), is_active=False,
            discount_base=CAMPAIGN_PRICE_SOURCE.CURRENT, strike_price_display=CAMPAIGN_PRICE_SOURCE.CURRENT,
        )
        rows = []
    else:
        rows = list(
            campaign.campaign_products.select_related("product__category")
            .prefetch_related("variant_discounts", "product__variants", "product__gift_product")
            .order_by("sort_order", "id")
        )

    cards = {c["id"]: c for c in product_cards([r.product for r in rows], now)}
    products = [{**cards[r.product_id], "row": _row_data(r)} for r in rows]

    def url(f):
        return f.url if f else ""

    return {
        "id": campaign.pk,
        "title": campaign.title,
        "slug": campaign.slug or "",
        "short_description": campaign.short_description,
        "hero_title": campaign.hero_title,
        "hero_subtitle": campaign.hero_subtitle,
        "hero_button_text": campaign.hero_button_text,
        "show_on_home": campaign.show_on_home,
        "show_in_slider": campaign.show_in_slider,
        "sort_order": campaign.sort_order,
        "start_at": local_str(campaign.start_at),
        "end_at": local_str(campaign.end_at),
        "is_active": campaign.is_active,
        "status": get_campaign_status(campaign, now) if campaign.pk else CAMPAIGN_STATUS.DRAFT,
        "discount_base": campaign.discount_base,
        "strike_price_display": campaign.strike_price_display,
        "price_surfaces": list(campaign.price_surfaces or []) if campaign.pk else list(CAMPAIGN_SURFACE.values),
        "badge_mode": campaign.badge_mode,
        "badge_label": campaign.badge_label if campaign.pk else "",
        "allow_coupon": campaign.allow_coupon,
        "include_product_gifts": campaign.include_product_gifts,
        "include_offers": campaign.include_offers,
        "allow_overlap": campaign.allow_overlap,
        "delivery_mode": campaign.delivery_mode,
        "delivery_amount_source": campaign.delivery_amount_source,
        "delivery_basis": campaign.delivery_basis,
        "mixed_cart_delivery": campaign.mixed_cart_delivery,
        "delivery_config": campaign.delivery_config or {},
        "images": {f: url(getattr(campaign, f)) for f in IMAGE_FIELDS},
        "products": products,
    }


class DashboardValidationError(Exception):
    def __init__(self, errors, conflicts=None):
        super().__init__("validation failed")
        self.errors = errors
        self.conflicts = conflicts or []


def _bool(value):
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _choice(value, enum, default):
    return value if value in enum.values else default


def _decimal(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _prepare_image(upload, max_width):
    if upload.size > IMAGE_MAX_BYTES:
        raise ValidationError("The image is larger than 8 MB.")
    try:
        img = Image.open(upload)
        img.verify()
        upload.seek(0)
        img = Image.open(upload)
        fmt = (img.format or "PNG").upper()
        if fmt not in ("PNG", "JPEG", "WEBP", "GIF"):
            raise ValidationError("Use a JPG, PNG, WEBP or GIF image.")
        if img.width <= max_width or fmt == "GIF":
            upload.seek(0)
            return upload
        height = round(img.height * max_width / img.width)
        img = img.resize((max_width, height), Image.LANCZOS)
        if fmt == "JPEG":
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format=fmt, quality=88, optimize=True)
        return ContentFile(buffer.getvalue(), name=upload.name)
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("This file is not a valid image.")


def _validate_product_rows(raw_rows, errors):
    if not isinstance(raw_rows, list):
        errors.setdefault("products", []).append("Products data is not valid.")
        return []

    ids = []
    for raw in raw_rows:
        try:
            ids.append(int(raw.get("product_id")))
        except (TypeError, ValueError, AttributeError):
            errors.setdefault("products", []).append("A product row is not valid.")
            return []
    products = {p.id: p for p in Product.objects.filter(id__in=ids).prefetch_related("variants")}

    rows, seen = [], set()
    for position, raw in enumerate(raw_rows):
        pid = int(raw["product_id"])
        product = products.get(pid)
        if product is None:
            errors.setdefault("products", []).append(f"Product #{pid} no longer exists.")
            continue
        name = product.name
        if pid in seen:
            errors.setdefault("products", []).append(f"'{name}' is added twice.")
            continue
        seen.add(pid)
        if product.status != CATEGORY_PRODUCT_STATUS.ACTIVE or product.is_gift_only:
            errors.setdefault("products", []).append(f"'{name}' is not an active, sellable product.")
            continue

        variants_active = active_variants(product)
        variant_mode = _choice(raw.get("variant_mode"), CAMPAIGN_VARIANT_MODE, CAMPAIGN_VARIANT_MODE.ALL_SAME)
        if not variants_active:
            variant_mode = CAMPAIGN_VARIANT_MODE.ALL_SAME
        dtype = _choice(raw.get("discount_type"), CAMPAIGN_DISCOUNT_TYPE, CAMPAIGN_DISCOUNT_TYPE.PERCENT)
        value = _decimal(raw.get("discount_value")) if str(raw.get("discount_value") or "").strip() else None

        variant_rows = []
        if variant_mode == CAMPAIGN_VARIANT_MODE.ALL_SAME:
            try:
                validate_discount(dtype, value)
            except ValidationError as exc:
                errors.setdefault("products", []).append(f"'{name}': {_first_message(exc)}")
                continue
        else:
            ok = True
            by_id = {v.id: v for v in variants_active}
            for vr in raw.get("variants") or []:
                vtext = str(vr.get("discount_value") if vr.get("discount_value") is not None else "").strip()
                if not vtext:
                    continue
                try:
                    variant = by_id[int(vr.get("variant_id"))]
                except (KeyError, TypeError, ValueError):
                    errors.setdefault("products", []).append(f"'{name}': a variant row is not valid.")
                    ok = False
                    continue
                vtype = _choice(vr.get("discount_type"), CAMPAIGN_DISCOUNT_TYPE, CAMPAIGN_DISCOUNT_TYPE.PERCENT)
                try:
                    validate_discount(vtype, _decimal(vtext))
                except ValidationError as exc:
                    errors.setdefault("products", []).append(f"'{name}' ({_variant_label(variant)}): {_first_message(exc)}")
                    ok = False
                    continue
                variant_rows.append({"variant": variant, "discount_type": vtype, "discount_value": _decimal(vtext)})
            if ok and not variant_rows:
                errors.setdefault("products", []).append(f"'{name}': give at least one variant a discount.")
                ok = False
            if not ok:
                continue

        stock_text = str(raw.get("stock_limit") if raw.get("stock_limit") is not None else "").strip()
        stock_limit = None
        if stock_text:
            if not stock_text.isdigit() or int(stock_text) < 1:
                errors.setdefault("products", []).append(f"'{name}': stock limit must be 1 or more (leave it empty for no limit).")
                continue
            stock_limit = int(stock_text)

        delivery_config = raw.get("delivery_config") or None
        try:
            validate_delivery_config(delivery_config)
        except ValidationError as exc:
            errors.setdefault("products", []).append(f"'{name}': delivery amount - {_first_message(exc)}")
            continue

        rows.append({
            "product": product, "sort_order": position, "is_active": bool(raw.get("is_active", True)),
            "discount_type": dtype, "discount_value": value if value is not None else Decimal("0"),
            "variant_mode": variant_mode, "stock_limit": stock_limit,
            "gift_mode": _choice(raw.get("gift_mode"), CAMPAIGN_SWITCH_MODE, CAMPAIGN_SWITCH_MODE.INHERIT),
            "offer_mode": _choice(raw.get("offer_mode"), CAMPAIGN_SWITCH_MODE, CAMPAIGN_SWITCH_MODE.INHERIT),
            "discount_base_override": _choice(raw.get("discount_base"), CAMPAIGN_PRICE_SOURCE, ""),
            "strike_price_override": _choice(raw.get("strike_price_display"), CAMPAIGN_PRICE_SOURCE, ""),
            "delivery_config": delivery_config or None,
            "variant_rows": variant_rows,
        })
    return rows


def _first_message(exc):
    if hasattr(exc, "message_dict"):
        return next(iter(exc.message_dict.values()))[0]
    return exc.messages[0]


def _overlap_message(conflicts):
    by_campaign = {}
    for c in conflicts:
        by_campaign.setdefault(c["campaign_id"], {"c": c, "products": []})["products"].append(c["product_name"])
    lines = []
    for item in by_campaign.values():
        c = item["c"]
        window = f"{timezone.localtime(c['start_at']):%d %b %Y %H:%M} - {timezone.localtime(c['end_at']):%d %b %Y %H:%M}"
        lines.append(f"Campaign '{c['campaign_title']}' ({window}) already contains: {', '.join(item['products'])}.")
    return lines


def save_campaign(data, files, user, campaign=None):
    errors = {}
    is_new = campaign is None
    c = Campaign() if is_new else campaign
    publish = _bool(data.get("publish"))

    title = (data.get("title") or "").strip()
    if not title:
        errors["title"] = ["Title is required."]
    elif len(title) > 255:
        errors["title"] = ["Title is too long (255 characters max)."]

    slug_in = slugify(data.get("slug") or "")
    if slug_in:
        clash = Campaign.objects.filter(slug=slug_in).exclude(pk=c.pk).first()
        if clash:
            errors["slug"] = [f"This link name is already used by the campaign '{clash.title}'. Type a different one."]
    badge_label = (data.get("badge_label") or "").strip()
    if len(badge_label) > BADGE_LABEL_MAX_LENGTH:
        errors["badge_label"] = [f"The name in the red tag can have {BADGE_LABEL_MAX_LENGTH} letters at most. Make it shorter."]

    start_at, end_at = parse_local_dt(data.get("start_at")), parse_local_dt(data.get("end_at"))
    if not start_at:
        errors["start_at"] = ["Start time is required."]
    if not end_at:
        errors["end_at"] = ["End time is required."]
    if start_at and end_at and end_at <= start_at:
        errors["end_at"] = ["End time must be after the start time."]

    delivery_mode = _choice(data.get("delivery_mode"), CAMPAIGN_DELIVERY_MODE, CAMPAIGN_DELIVERY_MODE.NORMAL)
    amount_source = _choice(data.get("delivery_amount_source"), CAMPAIGN_DELIVERY_AMOUNT_SOURCE,
                            CAMPAIGN_DELIVERY_AMOUNT_SOURCE.SAME_FOR_ALL)
    try:
        delivery_config = json.loads(data.get("delivery_config") or "{}")
    except ValueError:
        delivery_config = None
        errors["delivery_config"] = ["Delivery amounts are not valid."]
    if delivery_config is not None:
        try:
            validate_delivery_config(delivery_config)
        except ValidationError as exc:
            errors["delivery_config"] = exc.messages
    if delivery_mode == CAMPAIGN_DELIVERY_MODE.NORMAL:
        delivery_config = delivery_config or {}
    elif (delivery_config is not None and not delivery_config
          and amount_source == CAMPAIGN_DELIVERY_AMOUNT_SOURCE.SAME_FOR_ALL):
        errors["delivery_config"] = ["Enter the delivery amount (at least the 'all districts' charge)."]

    prepared, clear = {}, {}
    for field in IMAGE_FIELDS:
        clear[field] = _bool(data.get(f"clear_{field}"))
        upload = files.get(field) if files else None
        if upload:
            try:
                prepared[field] = _prepare_image(upload, IMAGE_MAX_WIDTH[field])
            except ValidationError as exc:
                errors[field] = exc.messages

    try:
        raw_rows = json.loads(data.get("products") or "[]")
    except ValueError:
        raw_rows = None
        errors["products"] = ["Products data is not valid."]
    rows = _validate_product_rows(raw_rows, errors) if raw_rows is not None else []
    if publish and raw_rows is not None and not raw_rows:
        errors.setdefault("products", []).append("Add at least one product before publishing the campaign.")

    c.title = title
    c.short_description = (data.get("short_description") or "").strip()[:500]
    c.hero_title = (data.get("hero_title") or "").strip()[:255]
    c.hero_subtitle = (data.get("hero_subtitle") or "").strip()[:500]
    c.hero_button_text = (data.get("hero_button_text") or "").strip()[:100]
    c.show_on_home = _bool(data.get("show_on_home"))
    c.show_in_slider = _bool(data.get("show_in_slider"))
    try:
        c.sort_order = int(data.get("sort_order") or 0)
    except ValueError:
        errors["sort_order"] = ["Position in the list must be a whole number, for example 1, 2 or 3."]
    if start_at:
        c.start_at = start_at
    if end_at:
        c.end_at = end_at
    c.is_active = publish
    c.discount_base = _choice(data.get("discount_base"), CAMPAIGN_PRICE_SOURCE, CAMPAIGN_PRICE_SOURCE.CURRENT)
    c.strike_price_display = _choice(data.get("strike_price_display"), CAMPAIGN_PRICE_SOURCE, CAMPAIGN_PRICE_SOURCE.CURRENT)
    c.price_surfaces = [s for s in CAMPAIGN_SURFACE.values if _bool(data.get("surface_" + s.lower()))]
    c.badge_mode = _choice(data.get("badge_mode"), CAMPAIGN_BADGE_MODE, CAMPAIGN_BADGE_MODE.DISCOUNT_ONLY)
    c.badge_label = badge_label or title[:BADGE_LABEL_MAX_LENGTH]
    c.allow_overlap = _bool(data.get("allow_overlap"))
    c.allow_coupon = _bool(data.get("allow_coupon"))
    c.include_product_gifts = _bool(data.get("include_product_gifts"))
    c.include_offers = _bool(data.get("include_offers"))
    c.delivery_mode = delivery_mode
    c.delivery_amount_source = amount_source
    c.delivery_basis = _choice(data.get("delivery_basis"), CAMPAIGN_DELIVERY_BASIS, CAMPAIGN_DELIVERY_BASIS.PER_ORDER)
    c.mixed_cart_delivery = _choice(data.get("mixed_cart_delivery"), CAMPAIGN_MIXED_CART_DELIVERY,
                                    CAMPAIGN_MIXED_CART_DELIVERY.COMBINED)
    if delivery_config is not None:
        c.delivery_config = delivery_config
    c.slug = slug_in or c.slug or (_unique_campaign_slug(title, exclude_pk=c.pk) if title else "")

    if publish and end_at and end_at <= timezone.now():
        errors["end_at"] = [ENDED_MESSAGE]

    conflicts = []
    if publish and start_at and end_at and rows:
        conflicts = find_overlap_conflicts(c, [r["product"].id for r in rows if r["is_active"]])
        if conflicts:
            errors.setdefault("products", []).extend(_overlap_message(conflicts))
            errors["products"].append("Open 'Extra settings' and turn on 'Allow these products in another campaign running at the "
                                      "same time' in BOTH campaigns, or change the dates or the products.")

    if errors:
        raise DashboardValidationError(errors, conflicts)

    old_files = {f: (getattr(c, f).name if getattr(c, f) else None) for f in IMAGE_FIELDS}
    with transaction.atomic():
        if is_new:
            c.created_by = user if getattr(user, "is_authenticated", False) else None
        for field in IMAGE_FIELDS:
            if field in prepared:
                setattr(c, field, prepared[field])
            elif clear[field]:
                setattr(c, field, None)
        c.save()

        existing = {cp.product_id: cp for cp in c.campaign_products.all()}
        keep = set()
        for r in rows:
            cp = existing.get(r["product"].id) or CampaignProduct(campaign=c, product=r["product"])
            for attr in ("sort_order", "is_active", "discount_type", "discount_value", "variant_mode", "stock_limit",
                         "gift_mode", "offer_mode", "discount_base_override", "strike_price_override", "delivery_config"):
                setattr(cp, attr, r[attr])
            cp.save()
            keep.add(cp.id)
            cp.variant_discounts.all().delete()
            if r["variant_mode"] == CAMPAIGN_VARIANT_MODE.PER_VARIANT:
                CampaignProductVariant.objects.bulk_create([
                    CampaignProductVariant(campaign_product=cp, variant=vr["variant"],
                                           discount_type=vr["discount_type"], discount_value=vr["discount_value"])
                    for vr in r["variant_rows"]
                ])
        c.campaign_products.exclude(id__in=keep).delete()

    for field, old in old_files.items():
        new = getattr(c, field).name if getattr(c, field) else None
        if old and old != new and default_storage.exists(old):
            default_storage.delete(old)

    return c, pricing_warnings(c)


def pricing_warnings(campaign):
    out = []
    rows = campaign.campaign_products.select_related("product").prefetch_related(
        "variant_discounts", "product__variants")
    for cp in rows:
        codes = set()
        product = cp.product
        lines = ([resolve_line_price(campaign, cp, product, v) for v in active_variants(product)]
                 if product.has_variants else [resolve_line_price(campaign, cp, product)])
        for line in lines:
            codes.update(line.warnings)
        if codes:
            out.append({"product": product.name, "problems": [WARNING_TEXT.get(code, code) for code in sorted(codes)]})
    return out


ENDED_MESSAGE = ("This campaign's end time has already passed. Edit it, choose a new start and end time in the "
                 "future, then publish it again.")


def activation_problems(campaign):
    problems = []
    if campaign.end_at and campaign.end_at <= timezone.now():
        problems.append(ENDED_MESSAGE)
    if not campaign.campaign_products.filter(is_active=True).exists():
        problems.append("Add at least one product before publishing the campaign.")
    probe = Campaign(pk=campaign.pk, is_active=True, start_at=campaign.start_at, end_at=campaign.end_at,
                     allow_overlap=campaign.allow_overlap)
    conflicts = find_overlap_conflicts(probe)
    if conflicts:
        problems.extend(_overlap_message(conflicts))
    return problems


def duplicate_campaign(source, user):
    new = Campaign.objects.get(pk=source.pk)
    new.pk = None
    new.id = None
    new.title = f"{source.title} (Copy)"[:255]
    new.slug = ""
    new.badge_label = source.badge_label
    new.is_active = False
    # A copy of a finished campaign must not be born "ended": move the same-length window to the next
    # full hour so it is a ready draft (change the dates in the form, then publish).
    if source.start_at and source.end_at:
        now = timezone.now()
        start = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        if source.start_at <= now or source.end_at <= now:
            new.start_at = start
            new.end_at = start + (source.end_at - source.start_at)
    new.created_by = user if getattr(user, "is_authenticated", False) else None
    new.slug = _unique_campaign_slug(new.title)
    for field in IMAGE_FIELDS:
        src = getattr(source, field)
        setattr(new, field, None)
        if src and default_storage.exists(src.name):
            with src.open("rb") as fh:
                getattr(new, field).save(os.path.basename(src.name), ContentFile(fh.read()), save=False)
    with transaction.atomic():
        new.save()
        for cp in source.campaign_products.prefetch_related("variant_discounts"):
            variant_rows = list(cp.variant_discounts.all())
            cp.pk = None
            cp.id = None
            cp.campaign = new
            cp.save()
            CampaignProductVariant.objects.bulk_create([
                CampaignProductVariant(campaign_product=cp, variant_id=vd.variant_id,
                                       discount_type=vd.discount_type, discount_value=vd.discount_value)
                for vd in variant_rows
            ])
    return new


def delete_campaign_files(campaign):
    for field in IMAGE_FIELDS:
        f = getattr(campaign, field)
        if f and default_storage.exists(f.name):
            default_storage.delete(f.name)