from http import HTTPStatus
import json
import json as pyjson
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, F, Count
from django.conf import settings

from pencilwoodbd.extra_module import resize_to_fixed, parse_decimal, parse_int, parse_bool, parse_delivery_charge_payload
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, ATTRIBUTE_TYPE, PRODUCT_TYPE, REVIEW_STATUS, INVENTORY_TYPE

from site_app.bd_districts import BD_DISTRICTS, SYSTEM_DEFAULT_DELIVERY_CHARGE
from site_app.models import SiteDeliveryChargeConfig, HomeSlider

# Models
from .models import (
    Product, Category, ProductImage, ProductVideo, Attribute, AttributeValue,
    ProductVariant, ProductDeliveryCharge, ProductFeature, ProductFAQ, ReviewSettings,
)
from order.models import Review
from authentication.models import Customer

# Forms
from .forms import ProductForm, ProductImageForm, ProductVideoForm


# ------------------ Stock Alert --------------
STOCK_ALERT_THRESHOLD = 10


class ProductListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, *args, **kwargs):
        products = Product.objects.select_related("category").annotate(
            variant_count=Count("variants")
        ).order_by("-created_at")

        categories = Category.objects.all().order_by("name")
        attributes = Attribute.objects.prefetch_related("values").all()
        attributes_data = [
            {"id": a.id, "name": a.name, "values": [{"id": v.id, "value": v.value} for v in a.values.all()]}
            for a in attributes
        ]

        search = request.GET.get("q", "").strip()
        category_id = request.GET.get("category")
        status_filter = request.GET.get("status")  # published / draft / discount / all

        if search:
            products = products.filter(
                Q(name__icontains=search)
                | Q(sku__icontains=search)
                | Q(short_description__icontains=search)
                | Q(category__name__icontains=search)
            ).distinct()

        if category_id:
            try:
                category = Category.objects.get(id=category_id)
                # include products in this category OR any of its children
                child_ids = list(category.children.values_list("id", flat=True))
                products = products.filter(category_id__in=[category.id, *child_ids])
            except Category.DoesNotExist:
                pass

        if status_filter == "published":
            products = products.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE)
        elif status_filter == "draft":
            products = products.filter(status=CATEGORY_PRODUCT_STATUS.DRAFT)
        elif status_filter == "discount":
            products = products.filter(discount_price__gt=0).exclude(discount_price=F("price"))

        # Counts for the top tabs (computed from full unfiltered set, not the filtered qs)
        base_qs = Product.objects.all()
        counts = {
            "all": base_qs.count(),
            "published": base_qs.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE).count(),
            "draft": base_qs.filter(status=CATEGORY_PRODUCT_STATUS.DRAFT).count(),
            "discount": base_qs.filter(discount_price__gt=0).exclude(discount_price=F("price")).count(),
        }

        per_page = parse_int(request.GET.get("per_page"), 6)
        paginator = Paginator(products, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "products": page_obj,
            "paginator": paginator,
            "page_obj": page_obj,
            "categories": categories,
            "attributes": attributes,
            "existing_variants_data": [],
            "attributes_data": pyjson.dumps(attributes_data),
            "current_search": search,
            "current_category": category_id or "",
            "current_status": status_filter or "all",
            "current_per_page": str(per_page),
            "product_counts": counts,
            "bd_districts": BD_DISTRICTS,
            "existing_delivery_charge_json": pyjson.dumps(SiteDeliveryChargeConfig.get_solo().area_and_charge or {}),
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
        }

        if request.htmx:
            return render(request, "db_product/partial/partial_product_list.html", context)

        return render(request, "db_product/product_list.html", context)


@login_required(login_url="admin_login")
def add_product(request):

    attributes = Attribute.objects.prefetch_related("values").all()
    attributes_data = [
        {"id": a.id, "name": a.name, "values": [{"id": v.id, "value": v.value} for v in a.values.all()]}
        for a in attributes
    ]

    valid_statuses = [c[0] for c in CATEGORY_PRODUCT_STATUS.choices]

    if request.method == "POST":
        try:
            with transaction.atomic():

                category = None
                category_id = request.POST.get("category")

                if category_id:
                    category = Category.objects.filter(id=category_id).first()

                try:
                    tag_ids = json.loads(request.POST.get("tags") or "[]")
                    tag_ids = [t["id"] for t in tag_ids if "id" in t]
                except (json.JSONDecodeError, TypeError):
                    tag_ids = []

                variant_data = request.POST.getlist("variants")
                parsed_variants = []
                for variant_json in variant_data:
                    try:
                        data = json.loads(variant_json)
                    except json.JSONDecodeError:
                        continue
                    variant_attrs = data.get("attributes") or {}
                    if not variant_attrs:
                        continue
                    parsed_variants.append(data)

                product_type = PRODUCT_TYPE.VARIABLE if parsed_variants else PRODUCT_TYPE.SIMPLE

                # ---- STATUS:
                # - "Save Draft" button (status_action == "Draft") ALWAYS forces Draft,
                #   regardless of what the dropdown has selected.
                # - "Publish" button (status_action == "Active") or any other/no
                #   button submission -> use whatever the dropdown ("status") has
                #   selected (Active, Deactive, Draft, Trash, etc).
                # ----
                status_action = request.POST.get("status_action")  # "Draft" / "Active" / None
                dropdown_status = request.POST.get("status")

                if status_action == "Draft":
                    status_value = CATEGORY_PRODUCT_STATUS.DRAFT
                elif dropdown_status in valid_statuses:
                    status_value = dropdown_status
                else:
                    status_value = CATEGORY_PRODUCT_STATUS.DRAFT

            
                default_variant_data = None
                if parsed_variants:
                    default_variant_data = next(
                        (d for d in parsed_variants if parse_bool(d.get("is_default"))),
                        parsed_variants[0],
                    )

                if parsed_variants:
                    product_price = parse_decimal(
                        default_variant_data.get("price"),
                        default=parse_decimal(request.POST.get("price")),
                    )
                    product_discount_price = parse_decimal(
                        default_variant_data.get("discount_price"),
                        default=parse_decimal(request.POST.get("discount_price")),
                    )
                    product_cost_price = parse_decimal(
                        default_variant_data.get("cost_price"),
                        default=parse_decimal(request.POST.get("cost_price")),
                    )
                else:
                    product_price = parse_decimal(request.POST.get("price"))
                    product_discount_price = parse_decimal(request.POST.get("discount_price"))
                    product_cost_price = parse_decimal(request.POST.get("cost_price"))

                
                inventory_type = request.POST.get("inventory_type", INVENTORY_TYPE.IN_STOCK)
                valid_inventory_types = [c[0] for c in INVENTORY_TYPE.choices]
                if inventory_type not in valid_inventory_types:
                    inventory_type = INVENTORY_TYPE.IN_STOCK

                if inventory_type == INVENTORY_TYPE.UNLIMITED:
                    inventory_qty_value = 0
                elif inventory_type == INVENTORY_TYPE.OUT_OF_STOCK:
                    inventory_qty_value = 0
                else:
                    inventory_qty_value = parse_int(request.POST.get("inventory_quantity"))

                product = Product.objects.create(
                    name=request.POST.get("name", "").strip(),
                    category=category,
                    short_description=request.POST.get("short_description", ""),
                    details=request.POST.get("details", ""),
                    price=product_price,
                    discount_price=product_discount_price,
                    cost_price=product_cost_price,
                    inventory_quantity=inventory_qty_value,
                    inventory_type=inventory_type,
                    status=status_value,
                    product_type=product_type,
                    enable_pixel_tracking=request.POST.get("enable_pixel_tracking") == "on",
                    facebook_pixel_id=request.POST.get("facebook_pixel_id", "").strip() or None,
                    gtm_container_id=request.POST.get("gtm_container_id", "").strip() or None,
                    ga4_measurement_id=request.POST.get("ga4_measurement_id", "").strip() or None,
                    seo={
                        "title": request.POST.get("seo_title", "").strip(),
                        "description": request.POST.get("seo_description", "").strip(),
                        "keywords": request.POST.get("seo_keywords", "").strip(),
                    },
                )
                hero_slider_image = request.FILES.get("hero_slider_image")
                if hero_slider_image:
                    resized = resize_to_fixed(hero_slider_image, settings.HERO_SLIDER_SIZE)
                    hero_slide, _ = HomeSlider.objects.update_or_create(
                        product=product,
                        defaults={
                            "title": product.name,
                            "image": resized,
                            "is_active": False,  # never auto-active — admin decides in Slider list
                        }
                    )
                # ---------------- Delivery Charge (per-product) ----------------
                area_and_charge, has_charge, delivery_charge_cost = parse_delivery_charge_payload(request)
                if has_charge or delivery_charge_cost is not None:
                    ProductDeliveryCharge.objects.update_or_create(
                        product=product,
                        defaults={
                            "area_and_charge": area_and_charge,
                            "delivery_charge_cost": delivery_charge_cost or 0,
                        },
                    )

                if not product.name:
                    raise ValueError("Product title is required.")

                if tag_ids:
                    product.tags.set(tag_ids)

                image_files = request.FILES.getlist("images")
                primary_image_id = request.POST.get("primary_image_index")

                for index, image in enumerate(image_files):
                    role = "primary" if (
                        primary_image_id is not None
                        and str(index) == str(primary_image_id)
                    ) else "gallery"

                    ProductImage.objects.create(
                        product=product,
                        image=image,
                        role=role,
                        position=index,
                    )

                if image_files and not product.images.filter(role="primary").exists():
                    first_img = product.images.order_by("position").first()
                    if first_img:
                        first_img.role = "primary"
                        first_img.save(update_fields=["role"])

                video = request.FILES.get("video")
                if video:
                    ProductVideo.objects.create(product=product, video=video)

                created_variants = []
                for data in parsed_variants:
                    variant_attrs = data.get("attributes") or {}
                    is_default_flag = parse_bool(data.get("is_default")) or (data is default_variant_data)
                    variant = ProductVariant.objects.create(
                        product=product,
                        attributes=variant_attrs,
                        price=parse_decimal(data.get("price"), default=product.price),
                        discount_price=parse_decimal(
                            data.get("discount_price"), default=product.discount_price
                        ),
                        cost_price=parse_decimal(
                            data.get("cost_price"), default=product.cost_price
                        ),
                        inventory_quantity=parse_int(data.get("inventory_quantity")),
                        is_active=data.get("is_active", True),
                        is_default=is_default_flag,
                    )
                    created_variants.append(variant)

                if product.has_variants:
                    product.inventory_quantity = sum(
                        v.inventory_quantity
                        for v in product.variants.filter(is_active=True)
                    )
                    product.save(update_fields=["inventory_quantity"])

                try:
                    features_raw = request.POST.get("features_json", "").strip()
                    if features_raw:
                        features_list = json.loads(features_raw)
                        for f in features_list:
                            title = (f.get("title") or "").strip()
                            description = (f.get("description") or "").strip()
                            if not title:
                                continue
                            ProductFeature.objects.create(
                                product=product,
                                icon=(f.get("icon") or "✔").strip(),
                                title=title,
                                description=description,
                                sort_order=int(f.get("sort_order") or 0),
                            )
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

                messages.success(request, "Product added successfully")
                return redirect("product_list")

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Failed to create product: {e}")

    return render(
        request,
        "db_product/add_product.html",
        {
            "categories": Category.objects.all(),
            "attributes": attributes,
            "attributes_data": pyjson.dumps(attributes_data),
            "existing_variants_data": "[]",
            "CATEGORY_PRODUCT_STATUS_CHOICES": CATEGORY_PRODUCT_STATUS.choices,
            "bd_districts": BD_DISTRICTS,
            "existing_delivery_charge_json": "{}",
            "existing_delivery_charge_cost": None,
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
        },
    )


@login_required(login_url="admin_login")
def product_update(request, pk):

    product = get_object_or_404(Product, pk=pk)

    attributes = Attribute.objects.prefetch_related("values").all()
    attributes_data = [
        {"id": a.id, "name": a.name, "values": [{"id": v.id, "value": v.value} for v in a.values.all()]}
        for a in attributes
    ]

    existing_variants_data = [
        {
            "id": v.id,
            "attributes": v.attributes,
            "price": str(v.price),
            "discount_price": str(v.discount_price),
            "cost_price": str(v.cost_price) if v.cost_price is not None else "",
            "inventory_quantity": v.inventory_quantity,
            "is_active": v.is_active,
            "is_default": v.is_default,
        }
        for v in product.variants.all()
    ]

    valid_statuses = [c[0] for c in CATEGORY_PRODUCT_STATUS.choices]

    if request.method == "POST":

        try:

            with transaction.atomic():

                category = None
                category_id = request.POST.get("category")

                if category_id:
                    category = Category.objects.filter(id=category_id).first()

                product.name = request.POST.get("name", product.name).strip()
                product.category = category
                product.short_description = request.POST.get("short_description", product.short_description)
                product.details = request.POST.get("details", product.details)

                status_action = request.POST.get("status_action")  # "Draft" / "Active" / None
                dropdown_status = request.POST.get("status")

                if status_action == "Draft":
                    status_value = CATEGORY_PRODUCT_STATUS.DRAFT
                elif dropdown_status in valid_statuses:
                    status_value = dropdown_status
                else:
                    status_value = product.status

                product.status = status_value
                product.enable_pixel_tracking = request.POST.get("enable_pixel_tracking") == "on"
                product.facebook_pixel_id = request.POST.get("facebook_pixel_id", "").strip() or None
                product.gtm_container_id = request.POST.get("gtm_container_id", "").strip() or None
                product.ga4_measurement_id = request.POST.get("ga4_measurement_id", "").strip() or None
                product.seo = {
                    "title": request.POST.get("seo_title", "").strip(),
                    "description": request.POST.get("seo_description", "").strip(),
                    "keywords": request.POST.get("seo_keywords", "").strip(),
                }

                product.save()

                hero_slider_image = request.FILES.get("hero_slider_image")
                delete_hero_slider = request.POST.get("delete_hero_slider_image")

                if delete_hero_slider:
                    for slider in HomeSlider.objects.filter(product=product):
                        slider.delete()
                elif hero_slider_image:
                    resized = resize_to_fixed(hero_slider_image, settings.HERO_SLIDER_SIZE)
                    HomeSlider.objects.update_or_create(
                        product=product,
                        defaults={
                            "title": product.name,
                            "image": resized,
                            "is_active": HomeSlider.objects.filter(product=product).values_list("is_active", flat=True).first() or False,
                        }
                    )
                else:
                    HomeSlider.objects.filter(product=product).update(title=product.name)

                # ---------------- Delivery Charge (per-product) ----------------
                area_and_charge, has_charge, delivery_charge_cost = parse_delivery_charge_payload(request)
                if has_charge or delivery_charge_cost is not None:
                    ProductDeliveryCharge.objects.update_or_create(
                        product=product,
                        defaults={
                            "area_and_charge": area_and_charge,
                            "delivery_charge_cost": delivery_charge_cost or 0,
                        },
                    )
                elif not has_charge:
                    ProductDeliveryCharge.objects.filter(product=product).delete()

                try:
                    tag_ids = json.loads(request.POST.get("tags") or "[]")
                    tag_ids = [t["id"] for t in tag_ids if "id" in t]
                except (json.JSONDecodeError, TypeError):
                    tag_ids = []
                product.tags.set(tag_ids)

                # ---------------- Images: delete selected ----------------
                delete_images = request.POST.getlist("delete_images")
                if delete_images:
                    ProductImage.objects.filter(id__in=delete_images, product=product).delete()

                # ---------------- Images: new uploads ----------------
                image_files = request.FILES.getlist("images")
                start_position = product.images.count()
                primary_image_id = request.POST.get("primary_image_index")

                new_image_objs = []
                for index, image in enumerate(image_files):
                    img = ProductImage.objects.create(
                        product=product,
                        image=image,
                        role="gallery",
                        position=start_position + index,
                    )
                    new_image_objs.append(img)

                # ---------------- Set primary from existing OR newly uploaded ----------------
                existing_primary_id = request.POST.get("existing_primary_image_id")
                if existing_primary_id:
                    ProductImage.objects.filter(product=product).update(role="gallery")
                    ProductImage.objects.filter(id=existing_primary_id, product=product).update(role="primary")
                elif primary_image_id is not None and new_image_objs:
                    try:
                        idx = int(primary_image_id)
                        if 0 <= idx < len(new_image_objs):
                            ProductImage.objects.filter(product=product).update(role="gallery")
                            new_image_objs[idx].role = "primary"
                            new_image_objs[idx].save(update_fields=["role"])
                    except (ValueError, TypeError):
                        pass

                if not product.images.filter(role="primary").exists():
                    first_img = product.images.order_by("position").first()
                    if first_img:
                        first_img.role = "primary"
                        first_img.save(update_fields=["role"])

                # ---------------- Video ----------------
                delete_video = request.POST.get("delete_video")
                if delete_video:
                    ProductVideo.objects.filter(id=delete_video, product=product).delete()

                video = request.FILES.get("video")
                if video:
                    ProductVideo.objects.filter(product=product).delete()
                    ProductVideo.objects.create(product=product, video=video)

                # ---------------- Variants ----------------
                variant_data = request.POST.getlist("variants")
                existing_ids = []
                parsed_variants = []

                for variant_json in variant_data:
                    data = json.loads(variant_json)
                    variant_attrs = data.get("attributes") or {}
                    if not variant_attrs:
                        continue
                    parsed_variants.append(data)

                # Figure out which variant (existing or new) should be default
                default_variant_data = None
                if parsed_variants:
                    default_variant_data = next(
                        (d for d in parsed_variants if parse_bool(d.get("is_default"))),
                        parsed_variants[0],
                    )

                for data in parsed_variants:
                    variant_id = data.get("id")
                    is_default_flag = parse_bool(data.get("is_default")) or (data is default_variant_data)

                    if variant_id:
                        variant = ProductVariant.objects.get(id=variant_id, product=product)
                        variant.attributes = data.get("attributes", {})
                        variant.price = parse_decimal(data.get("price"), default=variant.price)
                        variant.discount_price = parse_decimal(data.get("discount_price"), default=variant.discount_price)
                        variant.cost_price = parse_decimal(data.get("cost_price"), default=variant.cost_price or Decimal("0"))
                        variant.inventory_quantity = parse_int(data.get("inventory_quantity"), default=variant.inventory_quantity)
                        variant.is_active = data.get("is_active", variant.is_active)
                        variant.is_default = is_default_flag
                        variant.save()
                        existing_ids.append(variant.id)
                    else:
                        variant = ProductVariant.objects.create(
                            product=product,
                            attributes=data.get("attributes", {}),
                            price=parse_decimal(data.get("price"), default=product.price),
                            discount_price=parse_decimal(data.get("discount_price"), default=product.discount_price),
                            cost_price=parse_decimal(data.get("cost_price"), default=product.cost_price or Decimal("0")),
                            inventory_quantity=parse_int(data.get("inventory_quantity")),
                            is_active=data.get("is_active", True),
                            is_default=is_default_flag,
                        )
                        existing_ids.append(variant.id)

                ProductVariant.objects.filter(product=product).exclude(id__in=existing_ids).delete()

                product.product_type = PRODUCT_TYPE.VARIABLE if parsed_variants else PRODUCT_TYPE.SIMPLE
                product.has_variants = bool(parsed_variants)
                product.save(update_fields=["product_type", "has_variants"])

                if product.has_variants:
                    product.inventory_quantity = sum(
                        v.inventory_quantity
                        for v in product.variants.filter(is_active=True)
                    )
                    default_variant = product.variants.filter(is_default=True).first() \
                        or product.variants.first()
                    if default_variant:
                        product.price = default_variant.price
                        product.discount_price = default_variant.discount_price
                        product.cost_price = default_variant.cost_price
                    product.save(update_fields=["inventory_quantity", "price", "discount_price", "cost_price"])
                else:
                    inventory_type = request.POST.get("inventory_type", product.inventory_type)
                    valid_inventory_types = [c[0] for c in INVENTORY_TYPE.choices]
                    if inventory_type not in valid_inventory_types:
                        inventory_type = product.inventory_type

                    if inventory_type == INVENTORY_TYPE.UNLIMITED:
                        product.inventory_quantity = 0
                    elif inventory_type == INVENTORY_TYPE.OUT_OF_STOCK:
                        product.inventory_quantity = 0
                    else:
                        product.inventory_quantity = parse_int(request.POST.get("inventory_quantity"), default=product.inventory_quantity)

                    product.inventory_type = inventory_type
                    product.price = parse_decimal(request.POST.get("price"), default=product.price)
                    product.discount_price = parse_decimal(request.POST.get("discount_price"), default=product.discount_price)
                    product.cost_price = parse_decimal(request.POST.get("cost_price"), default=product.cost_price or Decimal("0"))
                    product.save(update_fields=["inventory_quantity", "inventory_type", "price", "discount_price", "cost_price"])

                messages.success(request, "Product updated successfully")
                return redirect("product_update", pk=product.pk)

        except Exception as e:
            messages.error(request, str(e))

    existing_variants_data_json = pyjson.dumps(existing_variants_data)
    attributes_data_json = pyjson.dumps(attributes_data)

    existing_delivery_charge = {}
    if hasattr(product, "delivery_charge"):
        existing_delivery_charge = product.delivery_charge.area_and_charge or {}

    return render(
        request,
        "db_product/add_product.html",
        {
            "product": product,
            "variants": product.variants.all(),
            "categories": Category.objects.all(),
            "attributes": attributes,
            "attributes_data": attributes_data_json,
            "existing_variants_data": existing_variants_data_json,
            "is_update": True,
            "CATEGORY_PRODUCT_STATUS_CHOICES": CATEGORY_PRODUCT_STATUS.choices,
            "product_tag_ids": pyjson.dumps(
                [{"id": t.id, "name": t.name} for t in product.tags.all()]
            ),
            "bd_districts": BD_DISTRICTS,
            "existing_delivery_charge_json": pyjson.dumps(existing_delivery_charge),
            "existing_delivery_charge_cost": (
                product.delivery_charge.delivery_charge_cost
                if hasattr(product, "delivery_charge") and product.delivery_charge
                else None
            ),
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
        }
    )


class ProductDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, pk):
        return redirect("product_list")

    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)

        linked_landing_pages = list(product.landing_page.values_list("title", flat=True))
        if linked_landing_pages:
            messages.warning(
                request,
                f"Note: '{product.name}' was linked to landing page(s): {', '.join(linked_landing_pages)}. "
                f"Those landing pages will now show no product — update or deactivate them separately."
            )

        for slider in HomeSlider.objects.filter(product=product):
            slider.delete()

        try:
            product.delete()
            messages.success(request, "Product deleted successfully!")
        except Exception as e:
            messages.error(request, f"Failed to delete product: {e}")

        return redirect("product_list")


class ProductDuplicateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, pk):
        return redirect("product_list")

    def post(self, request, pk, *args, **kwargs):
        original = get_object_or_404(Product, pk=pk)

        try:
            with transaction.atomic():
                new_product = Product.objects.get(pk=original.pk)
                new_product.pk = None
                new_product.id = None
                new_product._state.adding = True

                new_product.name = f"{original.name} (Copy)"
                new_product.slug = None                     # save() will auto-generate a fresh unique slug
                new_product.sku = ""                         # save() will auto-generate a new sku
                new_product.status = "draft"                 # safety: duplicated product starts as Draft
                new_product.sold_count = 0
                new_product.manual_sold_count = None
                new_product.has_variants = False              # will be reset to True automatically if variants exist
                new_product.description_json = list(original.description_json or [])
                new_product.dimensions = dict(original.dimensions or {})
                new_product.seo = dict(original.seo or {})
                new_product.metadata = dict(original.metadata or {})
                new_product.save()

                new_product.tags.set(original.tags.all())

                variant_map = {}
                for variant in original.variants.all():
                    old_variant_id = variant.pk
                    variant.pk = None
                    variant.id = None
                    variant._state.adding = True
                    variant.product = new_product
                    variant.sku = ""  
                    variant.attributes = dict(variant.attributes or {})
                    variant.dimensions = dict(variant.dimensions or {})
                    variant.save()
                    variant_map[old_variant_id] = variant

                for image in original.images.all():
                    new_image = ProductImage(
                        product=new_product,
                        variant=variant_map.get(image.variant_id) if image.variant_id else None,
                        role=image.role,
                        metadata=dict(image.metadata or {}),
                        position=image.position,
                    )
                    if image.image:
                        image.image.open("rb")
                        new_image.image.save(
                            image.image.name.split("/")[-1],
                            ContentFile(image.image.read()),
                            save=False,
                        )
                        image.image.close()
                    new_image.save()

                for video in original.videos.all():
                    new_video = ProductVideo(
                        product=new_product,
                        variant=variant_map.get(video.variant_id) if video.variant_id else None,
                        metadata=dict(video.metadata or {}),
                        position=video.position,
                    )
                    if video.video:
                        video.video.open("rb")
                        new_video.video.save(
                            video.video.name.split("/")[-1],
                            ContentFile(video.video.read()),
                            save=False,
                        )
                        video.video.close()
                    new_video.save()

                for feature in original.features.all():
                    ProductFeature.objects.create(
                        product=new_product,
                        icon=feature.icon,
                        title=feature.title,
                        description=feature.description,
                        sort_order=feature.sort_order,
                    )

                if hasattr(original, "delivery_charge") and original.delivery_charge:
                    ProductDeliveryCharge.objects.create(
                        product=new_product,
                        area_and_charge=dict(original.delivery_charge.area_and_charge or {})
                            if original.delivery_charge.area_and_charge else original.delivery_charge.area_and_charge,
                        delivery_charge_cost=original.delivery_charge.delivery_charge_cost,
                    )

            messages.success(request, f"Product '{original.name}' duplicated successfully as '{new_product.name}'!")

        except Exception as e:
            messages.error(request, f"Failed to duplicate product: {e}")

        return redirect("product_list")
# ------------------Product Features--------


class ProductFeatureView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        features = product.features.all().order_by("sort_order", "id")
        return render(request, "db_product/partial/partial_feature_list.html", {
            "product": product,
            "features": features,
        })

    def post(self, request, product_id):
        try:
            product = get_object_or_404(Product, id=product_id)
            data = request.POST
            feature_id = data.get("feature_id")

            icon = data.get("icon", "✔").strip() or "✔"
            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            sort_order = parse_int(data.get("sort_order"), 0)

            if not title:
                return JsonResponse({"status": False, "message": "Title is required"}, status=HTTPStatus.BAD_REQUEST)

            if feature_id:
                feature = get_object_or_404(ProductFeature, id=feature_id, product=product)
                feature.icon = icon
                feature.title = title
                feature.description = description
                feature.sort_order = sort_order
                feature.save()
                return JsonResponse({"status": True, "message": "Feature updated successfully"}, status=HTTPStatus.OK)

            new_feature = ProductFeature.objects.create(
                product=product, icon=icon, title=title,
                description=description, sort_order=sort_order,
            )
            return JsonResponse({"status": True, "message": "Feature added successfully", "feature_id": new_feature.id}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_product_feature(request, id):
    if request.method == "DELETE":
        try:
            feature = ProductFeature.objects.filter(id=id).first()
            if not feature:
                return JsonResponse({"status": False, "message": "Feature not found or already deleted."}, status=HTTPStatus.NOT_FOUND)
            feature.delete()
            return JsonResponse({"status": True, "message": "Feature deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": f"Failed to delete feature: {str(e)}"}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request method."}, status=HTTPStatus.BAD_REQUEST)


# ------------------Product FAQs (global + per-product)--------


class FAQManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        scope = request.GET.get("scope", "global")  # "global" or "product"
        product_id = request.GET.get("product_id")

        if scope == "product" and product_id:
            product = get_object_or_404(Product, id=product_id)
            faqs = ProductFAQ.objects.filter(product=product).order_by("sort_order", "id")
        else:
            product = None
            faqs = ProductFAQ.objects.filter(product__isnull=True).order_by("sort_order", "id")

        context = {
            "faqs": faqs,
            "scope": scope,
            "product": product,
            "products": Product.objects.order_by("name"),
        }

        if request.htmx:
            return render(request, "db_faq/partial/partial_faq_list.html", context)

        return render(request, "db_faq/faq_list.html", context)

    def post(self, request):
        try:
            data = request.POST
            faq_id = data.get("faq_id")
            scope = data.get("scope", "global")
            product_id = data.get("product_id")

            question = data.get("question", "").strip()
            answer = data.get("answer", "").strip()
            sort_order = parse_int(data.get("sort_order"), 0)
            is_active = data.get("is_active") == "on"

            if not question or not answer:
                return JsonResponse({"status": False, "message": "Question and answer are required"}, status=HTTPStatus.BAD_REQUEST)

            product = None
            if scope == "product":
                if not product_id:
                    return JsonResponse({"status": False, "message": "Select a product"}, status=HTTPStatus.BAD_REQUEST)
                product = get_object_or_404(Product, id=product_id)

            if faq_id:
                faq = get_object_or_404(ProductFAQ, id=faq_id)
                faq.product = product
                faq.question = question
                faq.answer = answer
                faq.sort_order = sort_order
                faq.is_active = is_active
                faq.save()
                return JsonResponse({"status": True, "message": "FAQ updated successfully"}, status=HTTPStatus.OK)

            ProductFAQ.objects.create(
                product=product, question=question, answer=answer,
                sort_order=sort_order, is_active=is_active,
            )
            return JsonResponse({"status": True, "message": "FAQ added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_faq(request, id):
    if request.method == "DELETE":
        try:
            faq = get_object_or_404(ProductFAQ, id=id)
            faq.delete()
            return JsonResponse({"status": True, "message": "FAQ deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


# ------------------Product Reviews--------


class ReviewManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        product_id = request.GET.get("product_id")
        status_filter = request.GET.get("status")

        reviews = Review.objects.select_related("product", "customer").order_by("-created_at")

        if product_id:
            reviews = reviews.filter(product_id=product_id)

        if status_filter and status_filter in [c[0] for c in REVIEW_STATUS.choices]:
            reviews = reviews.filter(status=status_filter)

        per_page = parse_int(request.GET.get("per_page"), 10)
        paginator = Paginator(reviews, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "reviews": page_obj,
            "paginator": paginator,
            "products": Product.objects.order_by("name"),
            "status_choices": REVIEW_STATUS.choices,
            "current_product": product_id or "",
            "current_status": status_filter or "",
        }

        if request.htmx:
            return render(request, "db_review/partial/partial_review_list.html", context)

        return render(request, "db_review/review_list.html", context)

    def post(self, request):
        try:
            data = request.POST
            review_id = data.get("review_id")

            product_id = data.get("product_id")
            customer_name = data.get("customer_name", "").strip()
            rating = parse_int(data.get("rating"), 5)
            title = data.get("title", "").strip()
            comment = data.get("comment", "").strip()
            review_status = data.get("status", REVIEW_STATUS.APPROVED)

            if rating < 1 or rating > 5:
                return JsonResponse({"status": False, "message": "Rating must be between 1 and 5"}, status=HTTPStatus.BAD_REQUEST)

            if review_id:
                review = get_object_or_404(Review, id=review_id)
                if product_id:
                    review.product = get_object_or_404(Product, id=product_id)
                review.rating = rating
                review.title = title
                review.comment = comment
                review.status = review_status
                review.save()
                return JsonResponse({"status": True, "message": "Review updated successfully"}, status=HTTPStatus.OK)

            if not product_id:
                return JsonResponse({"status": False, "message": "Select a product"}, status=HTTPStatus.BAD_REQUEST)

            product = get_object_or_404(Product, id=product_id)

            customer = None
            if customer_name:
                customer = Customer.objects.filter(name__iexact=customer_name).first()
                if not customer:
                    customer = Customer.objects.create(name=customer_name)

            Review.objects.create(
                product=product, customer=customer, rating=rating,
                title=title, comment=comment, status=review_status,
            )
            return JsonResponse({"status": True, "message": "Review added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_review(request, id):
    if request.method == "DELETE":
        try:
            review = get_object_or_404(Review, id=id)
            review.delete()
            return JsonResponse({"status": True, "message": "Review deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


class ReviewSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        settings_row = ReviewSettings.get_solo()
        return render(request, "db_review/review_settings.html", {"settings": settings_row})

    def post(self, request):
        settings_row = ReviewSettings.get_solo()
        settings_row.default_rating = parse_decimal(request.POST.get("default_rating"), Decimal("4.8"))
        settings_row.default_review_count = parse_int(request.POST.get("default_review_count"), 0)
        settings_row.save()
        messages.success(request, "Global review settings updated successfully.")
        return redirect("review_settings")

# ------------------Product SoldCount----------


class SoldCountSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        settings_row = ReviewSettings.get_solo()
        products = Product.objects.order_by("name")
        overridden_products = Product.objects.filter(
            use_global_sold_count=False, manual_sold_count__isnull=False
        ).order_by("name")

        context = {
            "settings": settings_row,
            "products": products,
            "overridden_products": overridden_products,
        }

        if request.htmx:
            return render(request, "db_product/partial/partial_sold_count_modal_content.html", context)

        return render(request, "db_product/sold_count_settings.html", context)

    def post(self, request):
        try:
            mode = request.POST.get("mode")  # "global" or "single"

            if mode == "global":
                value = parse_int(request.POST.get("global_sold_count"), 0)
                settings_row = ReviewSettings.get_solo()
                settings_row.default_sold_count = value
                settings_row.save()
                return JsonResponse({
                    "status": True,
                    "message": f"Global sold count set to {value}+ for all products."
                })

            elif mode == "single":
                product_id = request.POST.get("product_id")
                value = request.POST.get("sold_count")

                if not product_id:
                    return JsonResponse({"status": False, "message": "Please select a product"}, status=400)

                product = get_object_or_404(Product, id=product_id)

                if value is None or str(value).strip() == "":
                    # clear override -> fall back to global
                    product.manual_sold_count = None
                    product.use_global_sold_count = True
                else:
                    product.manual_sold_count = parse_int(value, 0)
                    product.use_global_sold_count = False

                product.save(update_fields=["manual_sold_count", "use_global_sold_count"])

                return JsonResponse({
                    "status": True,
                    "message": f"Sold count for '{product.name}' set to {product.display_sold_count}+."
                })

            else:
                return JsonResponse({"status": False, "message": "Invalid mode"}, status=400)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=400)


@login_required(login_url="admin_login")
def get_product_sold_count(request, id):
    try:
        product = get_object_or_404(Product, id=id)
        return JsonResponse({
            "status": True,
            "data": {
                "id": product.id,
                "name": product.name,
                "manual_sold_count": product.manual_sold_count,
                "use_global_sold_count": product.use_global_sold_count,
                "actual_sold_count": product.sold_count,
                "display_sold_count": product.display_sold_count,
            }
        })
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=400)
    

# ------------------Category--------


class CategoryView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        parent_id = request.GET.get("parent")
        parent_category = None

        if parent_id:
            parent_category = get_object_or_404(Category, id=parent_id)
            categories = Category.objects.filter(parent=parent_category).order_by("sort_order", "name")
        else:
            categories = Category.objects.filter(parent__isnull=True).order_by("sort_order", "name")

        context = {
            "categories": categories,
            "parent_category": parent_category,
            "all_categories": Category.objects.all().order_by("name"),
            "status_choices": CATEGORY_PRODUCT_STATUS.choices,
        }

        if request.htmx:
            return render(request, "db_category/partial/partial_category_list.html", context)

        return render(request, "db_category/category_list.html", context)

    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST

                name = data.get("name", "").strip()
                description = data.get("description", "").strip()
                icon = data.get("icon", "").strip()
                sort_order = parse_int(data.get("sort_order"), 0)
                status = data.get("status", CATEGORY_PRODUCT_STATUS.ACTIVE)
                seo_title = data.get("seo_title", "").strip()
                seo_description = data.get("seo_description", "").strip()
                banner_image = request.FILES.get("banner_image")

                parent = None
                parent_id = data.get("parent")

                if parent_id:
                    parent = Category.objects.filter(id=parent_id).first()

                category_id = data.get("category_id")

                if category_id:
                    category = get_object_or_404(Category, id=category_id)

                    if parent and (parent.id == category.id or self._is_descendant(parent, category)):
                        return JsonResponse(
                            {"status": False, "message": "A category cannot be its own parent or sub-category."},
                            status=HTTPStatus.BAD_REQUEST,
                        )

                    if not name:
                        return JsonResponse({"status": False, "message": "Category name is required"}, status=HTTPStatus.BAD_REQUEST)

                    category.name = name
                    category.parent = parent
                    category.description = description
                    category.icon = icon or None
                    category.sort_order = sort_order
                    category.status = status
                    category.seo_title = seo_title or None
                    category.seo_description = seo_description or None
                    if banner_image:
                        category.banner_image = banner_image
                    category.save()

                    return JsonResponse(
                        {"status": True, "message": "Category updated successfully"},
                        status=HTTPStatus.OK,
                    )

                if not name:
                    return JsonResponse(
                        {"status": False, "message": "Category name is required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )

                Category.objects.create(
                    name=name,
                    parent=parent,
                    description=description,
                    icon=icon or None,
                    sort_order=sort_order,
                    status=status,
                    seo_title=seo_title or None,
                    seo_description=seo_description or None,
                    banner_image=banner_image,
                )
                return JsonResponse(
                    {"status": True, "message": "Category added successfully"},
                    status=HTTPStatus.CREATED,
                )
        except Exception as e:
            return JsonResponse(
                {"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST
            )

    def _is_descendant(self, candidate_parent, category):
        node = candidate_parent
        while node is not None:
            if node.id == category.id:
                return True
            node = node.parent
        return False


@login_required(login_url="admin_login")
def get_category(request, id):
    try:
        category = get_object_or_404(Category, id=id)
        return JsonResponse(
            {
                "status": True,
                "category": {
                    "id": category.id,
                    "name": category.name,
                    "description": category.description,
                    "status": category.status,
                    "icon": category.icon,
                    "sort_order": category.sort_order,
                    "parent_id": category.parent_id,
                    "seo_title": category.seo_title,
                    "seo_description": category.seo_description,
                    "banner_image": category.banner_image.url if category.banner_image else None,
                },
            },
            status=HTTPStatus.OK,
        )
    except Exception as e:
        print("Exception", e)
        return JsonResponse(
            {"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST
        )


@login_required(login_url="admin_login")
def delete_category(request, id):
    if request.method == "DELETE":
        try:
            category = get_object_or_404(Category, id=id)
            category.delete()
            return JsonResponse(
                {"status": True, "message": "Category deleted successfully"},
                status=HTTPStatus.OK,
            )
        except Exception as e:
            print("Exception", e)
            return JsonResponse(
                {"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST
            )
    return JsonResponse(
        {"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST
    )


class AttributeView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        attributes = Attribute.objects.prefetch_related("values").all().order_by("name")
        return render(request, "db_attribute/attribute_list.html", {
            "attributes": attributes,
            "attribute_types": ATTRIBUTE_TYPE.choices,
        })

    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST
                attribute_id = data.get("attribute_id")

                name = data.get("name", "").strip()
                atype = data.get("type", ATTRIBUTE_TYPE.TEXT)
                is_variant = data.get("is_variant") == "on"
                is_filterable = data.get("is_filterable") == "on"

                if not name:
                    return JsonResponse({"status": False, "message": "Attribute name is required"}, status=HTTPStatus.BAD_REQUEST)

                if attribute_id:
                    attribute = get_object_or_404(Attribute, id=attribute_id)
                    attribute.name = name
                    attribute.type = atype
                    attribute.is_variant = is_variant
                    attribute.is_filterable = is_filterable
                    attribute.save()
                    return JsonResponse({"status": True, "message": "Attribute updated successfully"}, status=HTTPStatus.OK)

                Attribute.objects.create(
                    name=name,
                    type=atype,
                    is_variant=is_variant,
                    is_filterable=is_filterable,
                )
                return JsonResponse({"status": True, "message": "Attribute added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_attribute(request, id):
    if request.method == "DELETE":
        try:
            attribute = get_object_or_404(Attribute, id=id)
            attribute.delete()
            return JsonResponse({"status": True, "message": "Attribute deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


# ------------------Attribute Value--------


class AttributeValueView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, attribute_id):
        attribute = get_object_or_404(Attribute, id=attribute_id)
        values = attribute.values.all().order_by("sort_order", "value")
        return render(request, "db_attribute/attribute_value_list.html", {
            "attribute": attribute,
            "values": values,
        })

    def post(self, request, attribute_id):
        try:
            with transaction.atomic():
                attribute = get_object_or_404(Attribute, id=attribute_id)
                data = request.POST
                value_id = data.get("value_id")

                value = data.get("value", "").strip()
                hex_code = data.get("hex_code", "").strip()
                sort_order = parse_int(data.get("sort_order"), 0)

                if not value:
                    return JsonResponse({"status": False, "message": "Value is required"}, status=HTTPStatus.BAD_REQUEST)

                # hex_code optional for any attribute type - no type restriction
                if hex_code and not hex_code.startswith("#"):
                    hex_code = f"#{hex_code}"

                if value_id:
                    av = get_object_or_404(AttributeValue, id=value_id, attribute=attribute)

                    if AttributeValue.objects.filter(
                        attribute=attribute, value__iexact=value
                    ).exclude(id=av.id).exists():
                        return JsonResponse(
                            {"status": False, "message": "This value already exists for this attribute"},
                            status=HTTPStatus.BAD_REQUEST,
                        )

                    av.value = value
                    av.hex_code = hex_code or None
                    av.sort_order = sort_order
                    av.save()
                    return JsonResponse({"status": True, "message": "Attribute value updated successfully"}, status=HTTPStatus.OK)

                if AttributeValue.objects.filter(attribute=attribute, value__iexact=value).exists():
                    return JsonResponse({"status": False, "message": "This value already exists for this attribute"}, status=HTTPStatus.BAD_REQUEST)

                AttributeValue.objects.create(
                    attribute=attribute,
                    value=value,
                    hex_code=hex_code or None,
                    sort_order=sort_order,
                )
                return JsonResponse({"status": True, "message": "Attribute value added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_attribute_value(request, id):
    if request.method == "DELETE":
        try:
            av = get_object_or_404(AttributeValue, id=id)
            av.delete()
            return JsonResponse({"status": True, "message": "Attribute value deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)

# ------------------Order section CBV-------------


class StockAlertListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        view_mode = request.GET.get("view", "short")
        search = request.GET.get("q", "").strip()
        min_stock = request.GET.get("min_stock", "").strip()
        max_stock = request.GET.get("max_stock", "").strip()
        per_page = parse_int(request.GET.get("per_page"), 15)

        base_qs = Product.objects.exclude(inventory_type=INVENTORY_TYPE.UNLIMITED)

        if view_mode == "all":
            products = base_qs.order_by("inventory_quantity", "name")
        else:
            products = base_qs.filter(
                Q(inventory_type=INVENTORY_TYPE.OUT_OF_STOCK)
                | Q(inventory_type=INVENTORY_TYPE.IN_STOCK, inventory_quantity__lte=STOCK_ALERT_THRESHOLD)
            ).order_by("inventory_quantity", "name")

        if search:
            products = products.filter(Q(name__icontains=search) | Q(sku__icontains=search))

        if min_stock != "":
            products = products.filter(inventory_quantity__gte=parse_int(min_stock, 0))

        if max_stock != "":
            products = products.filter(inventory_quantity__lte=parse_int(max_stock, 0))

        paginator = Paginator(products, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "products": page_obj,
            "paginator": paginator,
            "view_mode": view_mode,
            "current_search": search,
            "current_min_stock": min_stock,
            "current_max_stock": max_stock,
            "current_per_page": str(per_page),
            "stock_alert_threshold": STOCK_ALERT_THRESHOLD,
        }
        return render(request, "db_home/partial/stock_alert_list.html", context)


