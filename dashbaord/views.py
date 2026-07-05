from http import HTTPStatus
import json
import random
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils.text import slugify
from django.utils import timezone
from django.urls import reverse_lazy

from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from decimal import Decimal, InvalidOperation
import json as pyjson


# Models
from order.models import Order, OrderRequest, OrderItem, OrderRequestItem
from product.models import Product, Category, ProductImage, ProductVideo, Attribute, AttributeValue, ProductVariant
from authentication.models import CustomUser
from site_app.models import DeliveryOption

# Forms
from product.forms import ProductForm, ProductImageForm, ProductVideoForm
from django.forms import modelformset_factory

# Utilities
from order.utils import SteadFastParcelAPI

# Choices
from pencilwoodbd.choices import USER_TYPE, STATUS, CATEGORY_PRODUCT_STATUS, DELIVERY_TYPE, ORDER_REQUEST_STATUS, PAYMENT_TYPE, PAYMENT_STATUS


# ------------------Dashboard--------
class DashboardView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get_today_order_count(self, orders):
        today = timezone.now().date()
        return orders.filter(created_at__date=today).count()

    def get_today_sales_amount(self, orders):
        today = timezone.now().date()
        return orders.filter(created_at__date=today).aggregate(
            total=Coalesce(Sum(F("order_items__discount_total_price") + F("shipping_total")), Value(0), output_field=DecimalField(max_digits=12, decimal_places=2))
        )["total"]

    def new_orders_count(self, orders):
        return orders.filter(status=STATUS.NEW).count()
    
    def new_order_request_count(self):
        return OrderRequest.objects.filter(
            status=ORDER_REQUEST_STATUS.PENDING
        ).count()

    def get_total_order_amount(self, orders):
        return orders.aggregate(
            total_amount=Coalesce(
                Sum(F("order_items__discount_total_price") + F("shipping_total")),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total_amount"]
    
    def get_status_amounts(self, orders):
        """Return a dict with total Tk per status"""
        amounts = {}
        for status_key, _ in STATUS.choices:
            amounts[status_key] = orders.filter(status=status_key).aggregate(
                total=Coalesce(
                    Sum(F("order_items__discount_total_price") + F("shipping_total")),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )["total"]
        
        # Add Returned + Refund combined total
        amounts["returned_refund"] = orders.filter(status__in=["returned", "refund"]).aggregate(
            total=Coalesce(
                Sum(F("order_items__discount_total_price") + F("shipping_total")),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        return amounts


    def get(self, request):
        orders = Order.objects.all().order_by("-created_at")

        is_staff = request.user.user_type == USER_TYPE.STAFF
        is_admin = request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

        context = {
            "orders": orders[:10],
            "today_order_count": self.get_today_order_count(orders),
            "new_orders_count": self.new_orders_count(orders),
            "status_amounts": self.get_status_amounts(orders),
            "total_orders": orders.count(),
            "new_order_request_count": self.new_order_request_count(),
        }

        if not is_staff:
            context["total_order_amount"] = self.get_total_order_amount(orders)
            context["today_sales_amount"] = self.get_today_sales_amount(orders)
        else:
            context["total_order_amount"] = None
            context["today_sales_amount"] = None

        if request.htmx:
            return render(request, "db_home/main_wrapper.html", context)

        return render(request, "dashboard.html", context)

class UserLoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "db_auth/login.html")

    def post(self, request):
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user = authenticate(username=email, password=password)
            if user is not None and user.user_type in (
                USER_TYPE.ADMIN,
                USER_TYPE.SUPER_ADMIN,
                USER_TYPE.STAFF,
            ):
                login(request, user)
                return redirect("dashboard")
            else:
                return render(
                    request,
                    "db_auth/login.html",
                    {"error": "Invalid credentials or insufficient permissions."},
                )
        except CustomUser.DoesNotExist:
            return render(
                request, "db_auth/login.html", {"error": "User does not exist."}
            )


class AdminLogoutView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        logout(request)
        return redirect("admin_login")


# ------------------Product--------
class ProductListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, *args, **kwargs):
        products = Product.objects.annotate(variant_count=Count("variants"))
        categories = Category.objects.all()
        attributes = Attribute.objects.prefetch_related("values").all()
        attributes_data = [
            {"id": a.id, "name": a.name, "values": [{"id": v.id, "value": v.value} for v in a.values.all()]}
            for a in attributes
        ]

        return render(request, "db_product/product_list.html", {
            "products": products,
            "categories": categories,
            "attributes": attributes,
            "attributes_data": attributes_data,
            "existing_variants_data": [],
        })

def parse_decimal(value, default=Decimal("0")):
    """Safely parse a POST value into Decimal, falling back on blank/invalid input."""
    if value is None or str(value).strip() == "":
        return default
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return default


def parse_int(value, default=0):
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@login_required(login_url="admin_login")
def add_product(request):

    attributes = Attribute.objects.prefetch_related("values").all()
    attributes_data = [
        {"id": a.id, "name": a.name, "values": [{"id": v.id, "value": v.value} for v in a.values.all()]}
        for a in attributes
    ]

    if request.method == "POST":
        try:
            with transaction.atomic():

                category = None
                category_id = request.POST.get("category")

                if category_id:
                    category = Category.objects.filter(id=category_id).first()

                # ---- Tags (safe parse) ----
                try:
                    tags = json.loads(request.POST.get("tags") or "[]")
                    if not isinstance(tags, list):
                        tags = []
                except json.JSONDecodeError:
                    tags = []

                product = Product.objects.create(
                    name=request.POST.get("name", "").strip(),
                    category=category,
                    short_description=request.POST.get("short_description", ""),
                    details=request.POST.get("details", ""),
                    price=parse_decimal(request.POST.get("price")),
                    discount_price=parse_decimal(request.POST.get("discount_price")),
                    inventory_quantity=parse_int(request.POST.get("inventory_quantity")),
                    status=request.POST.get("status", CATEGORY_PRODUCT_STATUS.DRAFT),
                    tags=tags,
                )

                if not product.name:
                    raise ValueError("Product title is required.")

                # ---------------- Images ----------------
                image_files = request.FILES.getlist("images")
                primary_image_id = request.POST.get("primary_image_index")  # optional, index-based

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

                # If nothing was explicitly marked primary, promote the first image
                if image_files and not product.images.filter(role="primary").exists():
                    first_img = product.images.order_by("position").first()
                    if first_img:
                        first_img.role = "primary"
                        first_img.save(update_fields=["role"])

                # ---------------- Video ----------------
                video = request.FILES.get("video")
                if video:
                    ProductVideo.objects.create(product=product, video=video)

                # ---------------- Variants ----------------
                variant_data = request.POST.getlist("variants")

                for variant_json in variant_data:
                    try:
                        data = json.loads(variant_json)
                    except json.JSONDecodeError:
                        continue  # skip malformed entries instead of crashing the whole request

                    variant_attrs = data.get("attributes") or {}
                    if not variant_attrs:
                        continue  # a variant with no attributes isn't meaningful

                    ProductVariant.objects.create(
                        product=product,
                        attributes=variant_attrs,
                        price=parse_decimal(data.get("price"), default=product.price),
                        discount_price=parse_decimal(
                            data.get("discount_price"), default=product.discount_price
                        ),
                        inventory_quantity=parse_int(data.get("inventory_quantity")),
                    )

                # ---------------- Recompute stock if variants exist ----------------
                if product.has_variants:
                    product.inventory_quantity = sum(
                        v.inventory_quantity
                        for v in product.variants.filter(is_active=True)
                    )
                    product.save(update_fields=["inventory_quantity"])

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
            "attributes_data": attributes_data,
            "existing_variants_data": [],
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
            "inventory_quantity": v.inventory_quantity,
            "is_active": v.is_active,
        }
        for v in product.variants.all()
    ]

    if request.method == "POST":

        try:

            with transaction.atomic():

                category = None

                category_id = request.POST.get("category")

                if category_id:
                    category = Category.objects.filter(
                        id=category_id
                    ).first()

                product.name = request.POST.get("name")
                product.category = category
                product.short_description = request.POST.get(
                    "short_description"
                )
                product.details = request.POST.get("details")
                product.price = request.POST.get("price") or 0
                product.discount_price = request.POST.get(
                    "discount_price"
                ) or 0

                product.status = request.POST.get(
                    "status",
                    product.status
                )

                product.tags = json.loads(
                    request.POST.get("tags", "[]")
                )

                product.save()

                # ---------------- Images ----------------

                delete_images = request.POST.getlist(
                    "delete_images"
                )

                if delete_images:
                    ProductImage.objects.filter(
                        id__in=delete_images,
                        product=product
                    ).delete()

                image_files = request.FILES.getlist("images")

                start_position = product.images.count()

                for index, image in enumerate(image_files):
                    ProductImage.objects.create(
                        product=product,
                        image=image,
                        role="gallery",
                        position=start_position + index
                    )

                # ---------------- Video ----------------

                delete_video = request.POST.get(
                    "delete_video"
                )

                if delete_video:
                    ProductVideo.objects.filter(
                        id=delete_video,
                        product=product
                    ).delete()

                video = request.FILES.get("video")

                if video:

                    ProductVideo.objects.filter(
                        product=product
                    ).delete()

                    ProductVideo.objects.create(
                        product=product,
                        video=video
                    )

                # ---------------- Variants ----------------

                variant_data = request.POST.getlist(
                    "variants"
                )

                existing_ids = []

                for variant_json in variant_data:

                    data = json.loads(variant_json)

                    variant_id = data.get("id")

                    if variant_id:

                        variant = ProductVariant.objects.get(
                            id=variant_id,
                            product=product
                        )

                        variant.attributes = data.get(
                            "attributes",
                            {}
                        )

                        variant.price = data.get(
                            "price",
                            variant.price
                        )

                        variant.discount_price = data.get(
                            "discount_price",
                            variant.discount_price
                        )

                        variant.inventory_quantity = data.get(
                            "inventory_quantity",
                            variant.inventory_quantity
                        )

                        variant.save()

                        existing_ids.append(
                            variant.id
                        )

                    else:

                        variant = ProductVariant.objects.create(
                            product=product,
                            attributes=data.get(
                                "attributes",
                                {}
                            ),
                            price=data.get(
                                "price",
                                product.price
                            ),
                            discount_price=data.get(
                                "discount_price",
                                product.discount_price
                            ),
                            inventory_quantity=data.get(
                                "inventory_quantity",
                                0
                            )
                        )

                        existing_ids.append(
                            variant.id
                        )

                ProductVariant.objects.filter(
                    product=product
                ).exclude(
                    id__in=existing_ids
                ).delete()

                if product.has_variants:

                    product.inventory_quantity = sum(
                        v.inventory_quantity
                        for v in product.variants.filter(
                            is_active=True
                        )
                    )

                    product.save(
                        update_fields=["inventory_quantity"]
                    )

                messages.success(
                    request,
                    "Product updated successfully"
                )

                return redirect("product_list")

        except Exception as e:

            messages.error(request, str(e))
            
    return render(
        request,
        "db_product/add_product.html",
        {
            "product": product,
            "variants": product.variants.all(),
            "categories": Category.objects.all(),
            "attributes": attributes,
            "attributes_data": attributes_data,
            "existing_variants_data": existing_variants_data,
            "is_update": True,
        }
    )

class ProductDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, pk):
        return redirect("product_list")

    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        product.delete()
        messages.success(request, "Product deleted successfully!")
        return redirect("product_list")


# ------------------Category--------
@login_required(login_url="admin_login")
def add_category(request):
    if request.method == "POST":
        Category.objects.create(
            name=request.POST.get("name"),
            slug=request.POST.get("slug"),
            parent=request.POST.get("parent"),
            status=request.POST.get("status"),
            image=request.FILES.get("image"),
        )
        return JsonResponse({"message": "Category added successfully"})
    return render(request, "db_category/add_category.html")


class CategoryView(View):
    def get(self, request):
        categories = Category.objects.all()
        return render(
            request, "db_category/category_list.html", {"categories": categories}
        )

    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST

                if data.get("category_id"):
                    category = Category.objects.get(id=data.get("category_id"))
                    category.name = data.get("category_title")
                    category.description = data.get("category_description")
                    category.save()
                    return JsonResponse(
                        {"status": True, "message": "Category updated successfully"},
                        status=HTTPStatus.OK,
                    )

                if data.get("category_title") == "":
                    return JsonResponse(
                        {"status": False, "message": "Category title is required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                if data.get("category_description") == "":
                    return JsonResponse(
                        {
                            "status": False,
                            "message": "Category description is required",
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                Category.objects.create(
                    name=data.get("category_title"),
                    description=data.get("category_description"),
                    status=CATEGORY_PRODUCT_STATUS.ACTIVE,
                )
                return JsonResponse(
                    {"status": True, "message": "Category added successfully"},
                    status=HTTPStatus.CREATED,
                )
        except Exception as e:
            print("Exception", e)
            return JsonResponse(
                {"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST
            )


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


# ------------------Order section CBV-------------
class AddOrderView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_order/add_order.html"

    def get(self, request):
        context = {
            "products": Product.objects.prefetch_related(
                "variants"
            ).order_by("name"),
            "categories": Category.objects.order_by("name"),
            "payment_types": PAYMENT_TYPE.choices,
            "delivery_types": DELIVERY_TYPE.choices,
            "status_choices": STATUS.choices,
        }

        return render(
            request,
            self.template_name,
            context,
        )

    def post(self, request):

        try:

            with transaction.atomic():

                data = request.POST

                shipping_address = data.get(
                    "shipping_address",
                    ""
                ).strip()

                note = data.get(
                    "note",
                    ""
                ).strip()

                payment_type = data.get(
                    "payment_type",
                    PAYMENT_TYPE.COD,
                )

                delivery_type = data.get(
                    "delivery_type",
                    DELIVERY_TYPE.HOME_DELIVERY,
                )

                status = data.get(
                    "status",
                    STATUS.NEW,
                )

                try:
                    shipping_total = Decimal(
                        data.get(
                            "shipping_total",
                            "0",
                        ) or "0"
                    )
                except (InvalidOperation, TypeError):
                    shipping_total = Decimal("0")

                try:
                    items = json.loads(
                        data.get(
                            "items",
                            "[]",
                        )
                    )
                except json.JSONDecodeError:
                    messages.error(
                        request,
                        "Invalid product data."
                    )
                    return redirect("add_order")

                if not items:
                    messages.error(
                        request,
                        "Please add at least one product.",
                    )
                    return redirect("add_order")

                order = Order.objects.create(
                    shipping_address=shipping_address,
                    note=note,
                    payment_type=payment_type,
                    delivery_type=delivery_type,
                    shipping_total=shipping_total,
                    payment_status=PAYMENT_STATUS.Unpaid,
                    status=status,
                )

                grand_total = shipping_total

                for item in items:

                    product = get_object_or_404(
                        Product,
                        id=item["product_id"],
                    )

                    variant = None

                    if item.get("variant_id"):

                        variant = get_object_or_404(
                            ProductVariant,
                            id=item["variant_id"],
                            product=product,
                        )

                    quantity = max(
                        int(item.get("quantity", 1)),
                        1,
                    )

                    if variant:

                        if variant.inventory_quantity < quantity:
                            raise Exception(
                                f"Insufficient stock for {product.name} ({variant})."
                            )

                        price = variant.price
                        discount_price = variant.discount_price

                    else:

                        if product.inventory_quantity < quantity:
                            raise Exception(
                                f"Insufficient stock for {product.name}."
                            )

                        price = product.price
                        discount_price = product.discount_price

                    final_price = (
                        discount_price
                        if discount_price
                        else price
                    )

                    line_total = final_price * quantity

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        variant=variant,
                        quantity=quantity,
                        price=price,
                        discount_price=discount_price,
                    )

                    grand_total += line_total

                order.total_cost = grand_total

                order.save(
                    update_fields=[
                        "total_cost",
                    ]
                )

                messages.success(
                    request,
                    f"Order {order.order_id} created successfully.",
                )

                return redirect(
                    "order_list"
                )

        except Exception as e:

            messages.error(
                request,
                str(e),
            )

            return redirect(
                "add_order"
            )

class OrderView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def status_wise_order_count(self):
        qs = (
            Order.objects
            .values("status")
            .annotate(total=Count("id"))
        )

        order_count = {
            status: 0
            for status, _ in STATUS.choices
        }

        for row in qs:
            order_count[row["status"]] = row["total"]

        order_count["all"] = sum(order_count.values())

        return order_count

    def get_order_queryset(self, request):

        order_status = request.GET.get("status")
        search = request.GET.get("q", "").strip()

        product_slug = request.GET.get("product")
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        orders = (
            Order.objects
            .select_related("customer")
            .prefetch_related(
                "order_items",
                "order_items__product",
                "order_items__variant",
            )
            .order_by("-created_at")
        )

        valid_status = {
            status
            for status, _ in STATUS.choices
        }

        if order_status in valid_status:
            orders = orders.filter(status=order_status)

        if product_slug:
            orders = orders.filter(
                Q(order_items__product__slug=product_slug)
                |
                Q(order_items__variant__product__slug=product_slug)
            ).distinct()

        if start_date and end_date:
            orders = orders.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )

        elif start_date:
            orders = orders.filter(
                created_at__date=start_date,
            )

        elif end_date:
            orders = orders.filter(
                created_at__date__lte=end_date,
            )

        if search:
            orders = orders.filter(
                Q(order_id__icontains=search)
                |
                Q(customer__name__icontains=search)
                |
                Q(customer__phone__icontains=search)
                |
                Q(shipping_address__icontains=search)
                |
                Q(status__iexact=search)
                |
                Q(payment_status__iexact=search)
                |
                Q(delivery_type__iexact=search)
            ).distinct()

        try:
            per_page = int(request.GET.get("per_page", 10))
        except (TypeError, ValueError):
            per_page = 10

        page_number = request.GET.get("page", 1)

        paginator = Paginator(
            orders,
            per_page,
        )

        orders = paginator.get_page(page_number)

        products = Product.objects.order_by("name")

        return (
            orders,
            paginator,
            per_page,
            page_number,
            products,
        )

    def get(self, request):

        (
            orders,
            paginator,
            per_page,
            page_number,
            products,
        ) = self.get_order_queryset(request)

        context = {
            "orders": orders,
            "paginator": paginator,
            "per_page": per_page,
            "page_number": page_number,

            "order_count": self.status_wise_order_count(),

            "current_status": request.GET.get(
                "status",
                "all",
            ),

            "current_search": request.GET.get(
                "q",
                "",
            ),

            "current_product_slug": request.GET.get(
                "product",
                "",
            ),

            "start_date": request.GET.get(
                "start_date",
                "",
            ),

            "end_date": request.GET.get(
                "end_date",
                "",
            ),

            "products": products,
        }

        if request.htmx:
            return render(
                request,
                "db_order/partial/partial_order_list.html",
                context,
            )

        return render(
            request,
            "db_order/order_list.html",
            context,
        )
    

class OrderDetailView(LoginRequiredMixin, View):
    def get(self, request, id):
        if not request.user.is_authenticated:
            return redirect("product_landing_page")
        elif request.user.user_type not in [
            USER_TYPE.ADMIN,
            USER_TYPE.STAFF,
            USER_TYPE.SUPER_ADMIN,
        ]:
            return redirect("product_landing_page")

        order = self.get_order(id)
        if request.htmx:
            return render(
                request, "db_order/partial/partial_order_detail.html", {"order": order}
            )
        return render(request, "db_order/order_detail.html", {"order": order})

    def get_order(self, id):
        return get_object_or_404(Order, id=id)

    def generate_unique_username(self, name):
        base = slugify(name) or "user"
        username = base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{username}-{counter}"
            counter += 1
        return username

    def update_customer_profile(self, data, profile):
        profile.full_name = data.get("full_name", profile.full_name)
        profile.phone = data.get("phone", profile.phone)
        if data.get("email"):
            if profile.user:
                profile.user.email = data.get("email", profile.user.email)
                profile.user.save()
            else:
                user = CustomUser.objects.create(
                    email=data.get("email"),
                    full_name=profile.full_name,
                    username=self.generate_unique_username(profile.full_name),
                )
                profile.user = user
        profile.save()
        return True

    def update_order_object(self, data, order):
        if data.get("delivery_date"):
            order.delivery_date = data.get("delivery_date", order.delivery_date)
        order.shipping_address = data.get("shipping_address", order.shipping_address)
        order.payment_status = data.get("payment_status", order.payment_status)
        order.order_status = data.get("order_status", order.order_status)
        
        if "note" in data:
            order.note = data.get("note", order.note)

        order.save()
        return True

    def post(self, request, id):
        if not request.user.is_authenticated:
            return redirect("product_landing_page")
        elif request.user.user_type not in [
            USER_TYPE.ADMIN,
            USER_TYPE.STAFF,
            USER_TYPE.SUPER_ADMIN,
        ]:
            return redirect("product_landing_page")
        if request.POST.get("_method") == "PATCH":
            return self.patch(request, id)
        return JsonResponse({"error": "Invalid request"}, status=400)

    def patch(self, request, id):
        order = self.get_order(id)

        data = request.POST
        print("data: ", data)
        if order:
            try:
                with transaction.atomic():
                    profile = order.customer
                    self.update_customer_profile(data, profile)
                    self.update_order_object(data, order)
                    return JsonResponse(
                        {"success": True, "message": "Order updated successfully"},
                        status=200,
                    )

            except Exception as e:
                print("error: ", e)
                return JsonResponse({"success": False, "message": str(e)})

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() == "patch":
            return self.patch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)


class OrderInvoiceView(View):
    def get_order(self, id):
        return get_object_or_404(Order, id=id)

    def get(self, request, id):
        print("id: ", id)
        order = self.get_order(id)
        if order:
            return render(request, "db_order/invoice.html", {"order": order})
        return redirect(request.META.get("HTTP_REFERER"))


def create_order_from_request(order_request):
    """
    Convert an OrderRequest into a real Order.
    """

    if order_request.status != ORDER_REQUEST_STATUS.PENDING:
        raise Exception("Only pending requests can be approved.")

    if order_request.converted_order:
        raise Exception("This request has already been converted.")

    with transaction.atomic():

        order = Order.objects.create(
            customer=order_request.customer,
            shipping_address=order_request.shipping_address,
            note=order_request.note,
            payment_type=order_request.payment_type,
            delivery_type=order_request.delivery_type,
            shipping_total=order_request.shipping_total,
            total_cost=order_request.total_cost,
        )

        for item in order_request.request_items.all():

            OrderItem.objects.create(
                order=order,
                product=item.product,
                variant=item.variant,
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                price=item.price,
                discount_price=item.discount_price,
                discount_total_price=item.discount_total_price,
                snapshot=item.snapshot,
            )

        order_request.status = ORDER_REQUEST_STATUS.CONVERTED
        order_request.converted_order = order
        order_request.converted_at = timezone.now()

        order_request.save(
            update_fields=[
                "status",
                "converted_order",
                "converted_at",
            ]
        )

    return order

class AddOrderRequestView(LoginRequiredMixin, View):
    login_url = "admin_login"

    template_name = "db_order_request/add_order_request.html"

    def get(self, request):
        context = {
            "products": Product.objects.prefetch_related(
                "variants",
                "category",
            ).order_by("name"),
            "categories": Category.objects.all().order_by("name"),
            "payment_types": PAYMENT_TYPE.choices,
            "delivery_types": DELIVERY_TYPE.choices,
        }

        return render(
            request,
            self.template_name,
            context,
        )

    def post(self, request):

        try:

            with transaction.atomic():

                data = request.POST

                shipping_address = data.get(
                    "shipping_address",
                    "",
                )

                note = data.get(
                    "note",
                    "",
                )

                payment_type = data.get(
                    "payment_type",
                    PAYMENT_TYPE.COD,
                )

                delivery_type = data.get(
                    "delivery_type",
                    DELIVERY_TYPE.HOME_DELIVERY,
                )

                shipping_total = float(
                    data.get(
                        "shipping_total",
                        0,
                    ) or 0
                )

                items = json.loads(
                    data.get(
                        "items",
                        "[]",
                    )
                )

                if not items:
                    messages.error(
                        request,
                        "Please add at least one product.",
                    )
                    return redirect(
                        "add_order_request"
                    )

                order_request = OrderRequest.objects.create(
                    shipping_address=shipping_address,
                    note=note,
                    payment_type=payment_type,
                    delivery_type=delivery_type,
                    shipping_total=shipping_total,
                )

                grand_total = shipping_total

                for item in items:

                    product = Product.objects.get(
                        id=item["product_id"]
                    )

                    variant = None

                    if item.get("variant_id"):

                        variant = ProductVariant.objects.get(
                            id=item["variant_id"],
                            product=product,
                        )

                    quantity = int(
                        item.get(
                            "quantity",
                            1,
                        )
                    )

                    price = (
                        variant.price
                        if variant
                        else product.price
                    )

                    discount_price = (
                        variant.discount_price
                        if variant
                        else product.discount_price
                    )

                    final_price = (
                        discount_price
                        if discount_price
                        else price
                    )

                    total = final_price * quantity

                    OrderRequestItem.objects.create(
                        order_request=order_request,
                        product=product,
                        variant=variant,
                        quantity=quantity,
                        price=price,
                        discount_price=discount_price,
                    )

                    grand_total += total

                order_request.total_cost = grand_total

                order_request.save(
                    update_fields=[
                        "total_cost",
                    ]
                )

                messages.success(
                    request,
                    "Order Request created successfully.",
                )

                return redirect(
                    "order_request_list"
                )

        except Exception as e:

            messages.error(
                request,
                str(e),
            )

            return redirect(
                "add_order_request"
            )
        

class OrderRequestListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def status_wise_request_count(self):
        qs = (
            OrderRequest.objects.values("status")
            .annotate(total=Count("id"))
        )

        request_count = {
            status: 0
            for status, _ in ORDER_REQUEST_STATUS.choices
        }

        for row in qs:
            request_count[row["status"]] = row["total"]

        request_count["all"] = sum(request_count.values())

        return request_count

    def get_request_queryset(self, request):

        status = request.GET.get("status")
        search = request.GET.get("q", "").strip()

        requests = (
            OrderRequest.objects
            .select_related(
                "customer",
                "converted_order",
            )
            .prefetch_related(
                "request_items",
            )
            .order_by("-created_at")
        )

        if status and status in [
            x[0] for x in ORDER_REQUEST_STATUS.choices
        ]:
            requests = requests.filter(status=status)

        if search:
            requests = requests.filter(
                Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(shipping_address__icontains=search)
                | Q(status__icontains=search)
                | Q(id__icontains=search)
            ).distinct()

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        if start_date and end_date:
            requests = requests.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )

        elif start_date:
            requests = requests.filter(
                created_at__date=start_date
            )

        elif end_date:
            requests = requests.filter(
                created_at__date__lte=end_date
            )

        page_number = request.GET.get("page", 1)
        per_page = int(request.GET.get("per_page", 10))

        paginator = Paginator(requests, per_page)
        requests = paginator.get_page(page_number)

        return (
            requests,
            paginator,
            per_page,
            page_number,
        )

    def get(self, request):

        (
            requests,
            paginator,
            per_page,
            page_number,
        ) = self.get_request_queryset(request)

        context = {
            "requests": requests,
            "paginator": paginator,
            "per_page": per_page,
            "page_number": page_number,

            "request_count": self.status_wise_request_count(),

            "current_status": request.GET.get(
                "status",
                "all",
            ),
            "current_search": request.GET.get(
                "q",
                "",
            ),
            "start_date": request.GET.get(
                "start_date",
                "",
            ),
            "end_date": request.GET.get(
                "end_date",
                "",
            ),
        }

        if request.htmx:
            return render(
                request,
                "db_order_request/partial/partial_order_request_list.html",
                context,
            )

        return render(
            request,
            "db_order_request/order_request_list.html",
            context,
        )
    

class OrderRequestDetailView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get_request(self, id):
        return get_object_or_404(
            OrderRequest.objects.select_related(
                "customer",
                "converted_order",
            ).prefetch_related(
                "request_items",
                "request_items__product",
                "request_items__variant",
            ),
            id=id,
        )

    def get(self, request, id):

        order_request = self.get_request(id)

        context = {
            "order_request": order_request,
        }

        if request.htmx:
            return render(
                request,
                "db_order_request/partial/partial_order_request_detail.html",
                context,
            )

        return render(
            request,
            "db_order_request/order_request_detail.html",
            context,
        )
    
class ApproveOrderRequestView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):

        order_request = get_object_or_404(
            OrderRequest,
            pk=pk,
        )

        try:

            order = create_order_from_request(
                order_request
            )

            messages.success(
                request,
                f"Order Request approved successfully. Order #{order.order_id} created."
            )

        except Exception as e:

            messages.error(
                request,
                str(e),
            )

        return redirect(
            "order_request_detail",
            id=pk,
        )
    
class RejectOrderRequestView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):

        order_request = get_object_or_404(
            OrderRequest,
            pk=pk,
        )

        if order_request.status != ORDER_REQUEST_STATUS.PENDING:

            messages.error(
                request,
                "Only pending requests can be rejected."
            )

            return redirect(
                "order_request_detail",
                id=pk,
            )

        order_request.status = ORDER_REQUEST_STATUS.CANCELLED

        order_request.save(
            update_fields=[
                "status",
            ]
        )

        messages.success(
            request,
            "Order Request cancelled successfully."
        )

        return redirect(
            "order_request_detail",
            id=pk,
        )
    
    
# ------------------Order section FBV-------------


@login_required(login_url="admin_login")
def update_order(request, order_id):
    if request.method != "POST" or request.POST.get("_method") != "PATCH":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    if request.user.user_type not in [
        USER_TYPE.ADMIN,
        USER_TYPE.STAFF,
        USER_TYPE.SUPER_ADMIN,
    ]:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )

    order = get_object_or_404(Order, id=order_id)
    data = request.POST

    def generate_unique_username(name):
        base = slugify(name) or "user"
        username = base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base}-{counter}"
            counter += 1
        return username

    try:
        with transaction.atomic():
            # Update customer profile
            profile = order.customer
            profile.name = data.get("full_name", profile.name)
            profile.phone = data.get("phone", profile.phone)
            profile.whatsapp = data.get("whatsapp", profile.phone)
            email = data.get("email")
            if email:
                if profile.user:
                    profile.user.email = email
                    profile.user.save()
                else:
                    user = CustomUser.objects.create(
                        email=email,
                        username=generate_unique_username(profile.name),
                        user_type=USER_TYPE.CUSTOMER,
                    )
                    profile.user = user
            profile.save()

            # Update order
            if data.get("delivery_date"):
                order.delivery_date = data.get("delivery_date")
            order.shipping_address = data.get(
                "shipping_address", order.shipping_address
            )
            order.payment_status = data.get("payment_status", order.payment_status)
            order.status = data.get("order_status", order.status)
            order.save()

            return JsonResponse(
                {"success": True, "message": "Order updated successfully"}, status=200
            )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


class OrderDeleteView(LoginRequiredMixin, DeleteView):
    model = Order
    success_url = reverse_lazy("order_list")
    login_url = "admin_login"

    def post(self, request, *args: str, **kwargs) -> HttpResponse:
        try:
            order = get_object_or_404(Order, pk=kwargs.get("pk"))
            order.delete()
            messages.success(request, "Order deleted successfully!")
        except:
            messages.error(request, "Order does not exist.")
        return redirect(request.META["HTTP_REFERER"])
        # return redirect(self.success_url)


class OrderDeliveryOptionSubmitView(LoginRequiredMixin, View):
    model = Order
    login_url = "admin_login"

    def get_order(self, id):
        try:
            return get_object_or_404(Order, id=id)
        except Exception as e:
            raise Exception(str(e))
    
    def get_order_data(self, order):
        email = (order.customer.email or order.customer.user.email if order.customer.user else None) or None
        whatsapp = order.customer.whatsapp if order.customer.whatsapp else None
        data = {
            "invoice": order.order_id,
            "recipient_name": order.customer.name,
            "recipient_phone": order.customer.phone,
            "recipient_address": order.shipping_address,
            "cod_amount": float(order.total_cost),
            "note": order.note,
            "total_lot": order.order_items.count(),
            "delivery_type": 1 if order.delivery_type == DELIVERY_TYPE.PICKUP else 0,
        }
        if whatsapp:
            data["alternative_phone"] = whatsapp
        if email:
            data["recipient_email"] = email
        return data
    
    def steadfast_response(self, logistics_partner, order):
        order_data = self.get_order_data(order)
        steadfast = SteadFastParcelAPI(logistics_partner.id)
        return steadfast.create_order(order_data)
        # return {
        #     "status": 200,
        #     "message": "Consignment has been created successfully.",
        #     "consignment": {
        #         "consignment_id": 1424107,
        #         "invoice": "Aa12-das4",
        #         "tracking_code": "15BAEB8A",
        #         "recipient_name": "John Smith",
        #         "recipient_phone": "01234567890",
        #         "recipient_address": "Fla# A1,House# 17/1, Road# 3/A, Dhanmondi,Dhaka-1209",
        #         "cod_amount": 1060,
        #         "status": "in_review",
        #         "note": "Deliver within 3PM",
        #         "created_at": "2021-03-21T07:05:31.000000Z",
        #         "updated_at": "2021-03-21T07:05:31.000000Z",
        #     },
        # }
    
    def get_logistics_partners(self, data):
        logistics_partner_id = data.get("logistics_partner")
        return DeliveryOption.objects.get(id=logistics_partner_id)
    
    def return_response(self, success, message, data=None, status=None) -> JsonResponse:
        response = {
            "success": success,
            "message": message,
        }
        if data:
            courier_name = data.courier.name if data.courier else None
            courier_type = data.courier.type if data.courier.type else None
            courier = f"{courier_name} ({courier_type})" if courier_name and courier_type else courier_name or courier_type or None
            response["data"] = {
                "id": data.id,
                "courier": courier,
                "tracking_number": data.tracking_number,
                "status": data.status,
                "updated_at": data.updated_at,
                "created_at": data.updated_at
            }
        return JsonResponse(
            response,
            status=status,
        )
    
    def post(self, request, *args: str, **kwargs):
        try:
            with transaction.atomic():
                data = json.loads(request.body)
                logistics_partner = self.get_logistics_partners(data)
                order = self.get_order(kwargs.get("pk"))
                steadfast_response = self.steadfast_response(logistics_partner, order)
                if steadfast_response.get("status") == 200:
                    order_shipped_data = order.shipments.create(
                        courier=logistics_partner,
                        tracking_number=steadfast_response["consignment"]["consignment_id"],
                        status=steadfast_response["consignment"]["status"],
                    )
                    return self.return_response(True, steadfast_response.get("message"), data=order_shipped_data, status=HTTPStatus.OK)
                else:
                    return self.return_response(False, steadfast_response.get("message"), status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            return self.return_response(False, f"{str(e)}", status=HTTPStatus.BAD_REQUEST)


# class RedirectView(View):
#     permanent = False
#     url = None
#     pattern_name = None
#     query_string = False

#     def get_redirect_url(self, *args, **kwargs):
#         if self.url:
#             url = self.url % kwargs
#         elif self.pattern_name:
#             url = reverse(self.pattern_name, args=args, kwargs=kwargs)
#         else:
#             return None

#         args = self.request.META.get("QUERY_STRING", "")
#         if args and self.query_string:
#             if urlparse(url).query:
#                 url = f"{url}&{args}"
#             else:
#                 url = f"{url}?{args}"
#         return url

#     def get(self, request, *args, **kwargs):
#         url = self.get_redirect_url(*args, **kwargs)
#         if url:
#             if self.permanent:
#                 return HttpResponsePermanentRedirect(url)
#             else:
#                 return HttpResponseRedirect(url)
#         else:
#             response = HttpResponseGone()
#             log_response("Gone: %s", request.path, response=response, request=request)
#             return response

#     def head(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

#     def post(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

#     def options(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

#     def delete(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)
