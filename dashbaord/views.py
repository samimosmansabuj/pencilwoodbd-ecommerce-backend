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
from django.contrib.auth.hashers import make_password


# Models
from order.models import Order, OrderRequest, OrderItem, OrderRequestItem
from product.models import Product, Category, ProductImage, ProductVideo, Attribute, AttributeValue, ProductVariant, Tag, ProductDeliveryCharge
from authentication.models import CustomUser, Customer
from site_app.models import DeliveryOption, SiteDeliveryChargeConfig

from site_app.bd_districts import BD_DISTRICTS, ALL_DISTRICTS_KEY, SYSTEM_DEFAULT_DELIVERY_CHARGE
from site_app.delivery_charge import DeliveryChargeResolver

# Forms
from product.forms import ProductForm, ProductImageForm, ProductVideoForm
from django.forms import modelformset_factory

# Utilities
from order.utils import SteadFastParcelAPI

# Choices
from pencilwoodbd.choices import USER_TYPE, STATUS, CATEGORY_PRODUCT_STATUS, DELIVERY_TYPE, ORDER_REQUEST_STATUS, PAYMENT_TYPE, PAYMENT_STATUS, ATTRIBUTE_TYPE, PRODUCT_TYPE, ORDER_REQUEST_WORK_STATUS


# ------------------Dashboard--------
class DashboardView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get_today_order_count(self, orders):
        today = timezone.now().date()
        return orders.filter(created_at__date=today).count()

    def get_today_sales_amount(self, orders):
        today = timezone.now().date()
        return orders.filter(created_at__date=today).aggregate(
            total=Coalesce(Sum(
                F("order_items__discount_price") * F("order_items__quantity") + F("shipping_total")
            ), Value(0), output_field=DecimalField(max_digits=12, decimal_places=2))
        )["total"]

    def new_orders_count(self, orders):
        return orders.filter(status=STATUS.NEW).count()
    
    def new_order_request_count(self):
        return OrderRequest.objects.filter(
            status=ORDER_REQUEST_STATUS.PENDING
        ).count()

    def get_total_order_amount(self, orders):
        items_total = OrderItem.objects.filter(order__in=orders).aggregate(
            total=Coalesce(
                Sum(F("discount_price") * F("quantity")),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        shipping_total = orders.aggregate(
            total=Coalesce(
                Sum("shipping_total"), Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        final_total = items_total + shipping_total
        return final_total
        # return orders.aggregate(
        #     total_amount=Coalesce(
        #         Sum(F("order_items__discount_total_price") + F("shipping_total")),
        #         Value(0),
        #         output_field=DecimalField(max_digits=12, decimal_places=2),
        #     )
        # )["total_amount"]
    
    def get_status_amounts(self, orders):
        """Return a dict with total Tk per status"""
        amounts = {}
        for status_key, _ in STATUS.choices:
            amounts[status_key] = orders.filter(status=status_key).aggregate(
                total=Coalesce(
                    Sum(F("order_items__discount_price") * F("order_items__quantity") + F("shipping_total")),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )["total"]
        
        # Add Returned + Refund combined total
        amounts["returned_refund"] = orders.filter(status__in=["returned", "refund"]).aggregate(
            total=Coalesce(
                Sum(F("order_items__discount_price") * F("order_items__quantity") + F("shipping_total")),
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

# ---------------User-----------------
class UserManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        tab = request.GET.get("tab", "customers")

        if tab == "staff":
            return self._staff_response(request)
        return self._customer_response(request)

    def _base_wrapper_context(self):
        """Provide the stats vars that main_wrapper.html expects."""
        orders = Order.objects.all().order_by("-created_at")
        dashboard_view = DashboardView()
        return {
            "status_amounts": dashboard_view.get_status_amounts(orders),
            "today_order_count": dashboard_view.get_today_order_count(orders),
            "new_orders_count": dashboard_view.new_orders_count(orders),
            "total_orders": orders.count(),
            "new_order_request_count": dashboard_view.new_order_request_count(),
        }

    def _customer_response(self, request):
        search = request.GET.get("q", "").strip()
        source = request.GET.get("source", "").strip()

        customers = Customer.objects.select_related("user").order_by("-created_at")

        if search:
            customers = customers.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(second_phone__icontains=search)
                | Q(email__icontains=search)
                | Q(company__icontains=search)
            ).distinct()

        if source:
            customers = customers.filter(source__iexact=source)

        per_page = parse_int(request.GET.get("per_page"), 10)
        paginator = Paginator(customers, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        sources = (
            Customer.objects.exclude(source__isnull=True)
            .exclude(source__exact="")
            .values_list("source", flat=True)
            .distinct()
            .order_by("source")
        )

        context = {
            "active_tab": "customers",
            "customers": page_obj,
            "paginator": paginator,
            "current_search": search,
            "current_source": source,
            "current_per_page": str(per_page),
            "sources": sources,
        }

        if request.htmx:
            return render(request, "db_users/partial/partial_customer_list.html", context)

        context.update(self._base_wrapper_context())
        return render(request, "db_users/user_management.html", context)

    def _staff_response(self, request):
        search = request.GET.get("q", "").strip()
        role = request.GET.get("role", "").strip()

        staff_users = CustomUser.objects.exclude(user_type=USER_TYPE.CUSTOMER).order_by("-date_joined")

        if search:
            staff_users = staff_users.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            ).distinct()

        valid_roles = [c[0] for c in USER_TYPE.choices]
        if role in valid_roles and role != USER_TYPE.CUSTOMER:
            staff_users = staff_users.filter(user_type=role)

        per_page = parse_int(request.GET.get("per_page"), 10)
        paginator = Paginator(staff_users, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        role_choices = [c for c in USER_TYPE.choices if c[0] != USER_TYPE.CUSTOMER]

        context = {
            "active_tab": "staff",
            "staff_users": page_obj,
            "paginator": paginator,
            "current_search": search,
            "current_role": role,
            "current_per_page": str(per_page),
            "role_choices": role_choices,
        }

        if request.htmx:
            return render(request, "db_users/partial/partial_staff_list.html", context)

        context.update(self._base_wrapper_context())
        return render(request, "db_users/user_management.html", context)
    

class StaffCreateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def _can_manage_staff(self, request):
        return request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

    def post(self, request):
        if not self._can_manage_staff(request):
            messages.error(request, "You don't have permission to create staff/admin users.")
            return redirect("user_management")

        data = request.POST
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")
        role = data.get("user_type", "").strip()

        redirect_url = f"{reverse_lazy('user_management')}?tab=staff"
        assignable_roles = [USER_TYPE.STAFF, USER_TYPE.ADMIN]

        if not username or not email or not password:
            messages.error(request, "Username, email and password are required.")
            return redirect(redirect_url)

        if role not in assignable_roles:
            messages.error(request, "Invalid role selected.")
            return redirect(redirect_url)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect(redirect_url)

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered.")
            return redirect(redirect_url)

        try:
            with transaction.atomic():
                user = CustomUser.objects.create(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    user_type=role,
                    password=make_password(password),
                    is_active=True,
                    is_staff=True,  # allows Django-admin login if ever needed
                )
            messages.success(request, f"{user.get_user_type_display()} account for '{username}' created successfully.")
        except Exception as e:
            messages.error(request, f"Failed to create user: {e}")

        return redirect(redirect_url)
    

class StaffUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def _can_manage_staff(self, request):
        return request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

    def get(self, request, pk):
        # Only admins can edit others; a user can edit only themselves otherwise
        target = get_object_or_404(CustomUser, pk=pk)
        if not self._can_manage_staff(request) and request.user.pk != target.pk:
            return JsonResponse({"status": False, "message": "Permission denied"}, status=HTTPStatus.FORBIDDEN)

        return JsonResponse({
            "status": True,
            "user": {
                "id": target.id,
                "username": target.username,
                "email": target.email,
                "first_name": target.first_name,
                "last_name": target.last_name,
                "user_type": target.user_type,
                "is_active": target.is_active,
            }
        })

    def post(self, request, pk):
        target = get_object_or_404(CustomUser, pk=pk)
        is_self = request.user.pk == target.pk
        is_manager = self._can_manage_staff(request)

        if not is_manager and not is_self:
            messages.error(request, "You don't have permission to edit this user.")
            return redirect("user_management")

        redirect_url = f"{reverse_lazy('user_management')}?tab=staff"
        data = request.POST

        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")
        role = data.get("user_type", "").strip()

        if not username or not email:
            messages.error(request, "Username and email are required.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(username=username).exclude(pk=target.pk).exists():
            messages.error(request, "This username is already taken.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(email=email).exclude(pk=target.pk).exists():
            messages.error(request, "This email is already registered.")
            return redirect(redirect_url)

        # Role change: only a manager can change roles, and never to/from SUPER_ADMIN via this form
        if is_manager:
            assignable_roles = [USER_TYPE.STAFF, USER_TYPE.ADMIN]
            if role and target.user_type != USER_TYPE.SUPER_ADMIN:
                if role not in assignable_roles:
                    messages.error(request, "Invalid role selected.")
                    return redirect(redirect_url)
                target.user_type = role
            # is_active toggle, manager only
            target.is_active = data.get("is_active") == "on"

        # Password change (optional on edit)
        if password or confirm_password:
            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return redirect(redirect_url)
            if len(password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return redirect(redirect_url)
            target.password = make_password(password)

        target.username = username
        target.email = email
        target.first_name = first_name
        target.last_name = last_name

        try:
            target.save()
            messages.success(request, f"User '{target.username}' updated successfully.")
        except Exception as e:
            messages.error(request, f"Failed to update user: {e}")

        return redirect(redirect_url)
    

# ------------------Product--------
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


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "on", "yes")


def parse_delivery_charge_payload(request):
    """
    Expects the form to submit a hidden JSON field: delivery_charge_json
    Shape sent from frontend JS:
        {"mode": "all", "all": "150"}
        or
        {"mode": "per_district", "Dhaka": "80", "Chattogram": "120", "all": "150"}
        or
        {"mode": "none"}   -> means "don't set any product-level charge, use global/system default"
 
    Returns (area_and_charge_dict_or_None, has_any_charge_bool)
    `None` means: delete/skip ProductDeliveryCharge entirely for this product.
    """
    raw = request.POST.get("delivery_charge_json", "").strip()
    if not raw:
        return None, False
 
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, False
 
    mode = payload.get("mode", "none")
    if mode == "none":
        return None, False
 
    area_and_charge = {}
    for key, value in payload.items():
        if key == "mode":
            continue
        parsed = parse_decimal(value, default=None)
        if parsed is not None:
            # store as string for clean JSON (Decimal isn't JSON serializable)
            area_and_charge[key] = str(parsed)
 
    if not area_and_charge:
        return None, False
 
    return area_and_charge, True

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

                # Determine the "default/featured" variant's price upfront so it can
                # seed Product.price / Product.discount_price / Product.cost_price
                # even for variable products.
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

                product = Product.objects.create(
                    name=request.POST.get("name", "").strip(),
                    category=category,
                    short_description=request.POST.get("short_description", ""),
                    details=request.POST.get("details", ""),
                    price=product_price,
                    discount_price=product_discount_price,
                    cost_price=product_cost_price,
                    inventory_quantity=parse_int(request.POST.get("inventory_quantity")),
                    status=status_value,
                    product_type=product_type,
                )

                # ---------------- Delivery Charge (per-product) ----------------
                area_and_charge, has_charge = parse_delivery_charge_payload(request)
                if has_charge:
                    ProductDeliveryCharge.objects.update_or_create(
                        product=product,
                        defaults={"area_and_charge": area_and_charge},
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
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
        },
    )


@login_required(login_url="admin_login")
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

                product.save()

                # ---------------- Delivery Charge (per-product) ----------------
                area_and_charge, has_charge = parse_delivery_charge_payload(request)
                if has_charge:
                    ProductDeliveryCharge.objects.update_or_create(
                        product=product,
                        defaults={"area_and_charge": area_and_charge},
                    )
                else:
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
                    # Sync Product.price/discount_price/cost_price with the default variant
                    default_variant = product.variants.filter(is_default=True).first() \
                        or product.variants.first()
                    if default_variant:
                        product.price = default_variant.price
                        product.discount_price = default_variant.discount_price
                        product.cost_price = default_variant.cost_price
                    product.save(update_fields=["inventory_quantity", "price", "discount_price", "cost_price"])
                else:
                    product.inventory_quantity = parse_int(request.POST.get("inventory_quantity"), default=product.inventory_quantity)
                    product.price = parse_decimal(request.POST.get("price"), default=product.price)
                    product.discount_price = parse_decimal(request.POST.get("discount_price"), default=product.discount_price)
                    product.cost_price = parse_decimal(request.POST.get("cost_price"), default=product.cost_price or Decimal("0"))
                    product.save(update_fields=["inventory_quantity", "price", "discount_price", "cost_price"])

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
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
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

class DeliveryChargeSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"
 
    def _can_manage(self, request):
        return request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]
 
    def get(self, request):
        config = SiteDeliveryChargeConfig.get_solo()
 
        context = {
            "bd_districts": BD_DISTRICTS,
            "existing_delivery_charge_json": pyjson.dumps(config.area_and_charge or {}),
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
        }
 
        if request.htmx:
            return render(request, "db_settings/partial/partial_delivery_charge_settings.html", context)
 
        return render(request, "db_settings/delivery_charge_settings.html", context)
 
    def post(self, request):
        if not self._can_manage(request):
            messages.error(request, "You don't have permission to change global delivery charges.")
            return redirect("delivery_charge_settings")
 
        area_and_charge, has_charge = parse_delivery_charge_payload(request)
 
        config = SiteDeliveryChargeConfig.get_solo()
        config.area_and_charge = area_and_charge or {}
        config.save()
 
        messages.success(request, "Global delivery charge settings updated successfully.")
        return redirect("delivery_charge_settings")
# ------------------Attribute--------
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
def build_variants_by_product(products):
    data = {}
    for product in products:
        variants = product.variants.filter(is_active=True)
        if variants.exists():
            data[str(product.id)] = [
                {
                    "id": v.id,
                    "attributes": v.attributes,
                    "price": str(v.price),
                    "discount_price": str(v.discount_price),
                    "inventory_quantity": v.inventory_quantity,
                    "sku": v.sku,
                }
                for v in variants
            ]
    return data


class AddOrderView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_order/add_order.html"

    def get(self, request):
        products = Product.objects.prefetch_related("variants").order_by("name")
        assignable_users = CustomUser.objects.filter(
            user_type__in=[USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN, USER_TYPE.STAFF]
        ).order_by("username")
        context = {
            "products": products,
            "categories": Category.objects.order_by("name"),
            "payment_types": PAYMENT_TYPE.choices,
            "delivery_types": DELIVERY_TYPE.choices,
            "status_choices": STATUS.choices,
            "variants_by_product_json": pyjson.dumps(build_variants_by_product(products)),
            "assignable_users": assignable_users,
            "existing_items_json": "[]",
            "is_update": False,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST

                company = data.get("company", "").strip()
                name = data.get("name", "").strip()
                email = data.get("email", "").strip()
                phone = data.get("phone", "").strip()
                second_phone = data.get("second_phone", "").strip()
                source = data.get("source", "Others").strip()

                if not name:
                    messages.error(request, "Customer name is required.")
                    return redirect("add_order")
                if not phone:
                    messages.error(request, "Phone number is required.")
                    return redirect("add_order")

                customer = Customer.objects.create(
                    company=company or None,
                    name=name,
                    phone=phone,
                    second_phone=second_phone or None,
                    email=email or None,
                    source=source or "Others",
                )

                shipping_address = data.get("shipping_address", "").strip()
                note = data.get("note", "").strip()
                special_instructions = data.get("special_instructions", "").strip()

                work_assign_id = data.get("work_assign") or None
                assigned_user = None
                if work_assign_id:
                    assigned_user = CustomUser.objects.filter(id=work_assign_id).first()

                payment_type = data.get("payment_type", PAYMENT_TYPE.COD)
                delivery_type = data.get("delivery_type", DELIVERY_TYPE.HOME_DELIVERY)
                status = data.get("status", STATUS.NEW)
                is_urgent = data.get("is_urgent") == "on"

                order_created_date = data.get("order_created_date") or None
                delivery_date = data.get("delivery_date") or None

                shipping_total = parse_decimal(data.get("shipping_total"))
                advance_amount = parse_decimal(data.get("advance_amount"))

                design_file = request.FILES.get("design_file")

                try:
                    items = json.loads(data.get("items", "[]"))
                except json.JSONDecodeError:
                    messages.error(request, "Invalid product data.")
                    return redirect("add_order")

                if not items:
                    messages.error(request, "Please add at least one product.")
                    return redirect("add_order")

                order = Order.objects.create(
                    customer=customer,
                    shipping_address=shipping_address,
                    note=note,
                    special_instructions=special_instructions or None,
                    work_assign=assigned_user.username if assigned_user else None,
                    payment_type=payment_type,
                    delivery_type=delivery_type,
                    shipping_total=shipping_total,
                    advance_amount=advance_amount,
                    payment_status=PAYMENT_STATUS.Unpaid,
                    status=status,
                    is_urgent=is_urgent,
                    order_created_date=order_created_date,
                    delivery_date=delivery_date,
                    design_file=design_file,
                )

                grand_total = shipping_total

                for item in items:
                    product = get_object_or_404(Product, id=item["product_id"])
                    variant = None
                    if item.get("variant_id"):
                        variant = get_object_or_404(ProductVariant, id=item["variant_id"], product=product)

                    quantity = max(int(item.get("quantity", 1)), 1)

                    if variant:
                        if variant.inventory_quantity < quantity:
                            raise Exception(f"Insufficient stock for {product.name} ({variant}).")
                        price = variant.price
                        discount_price = variant.discount_price
                    else:
                        if product.inventory_quantity < quantity:
                            raise Exception(f"Insufficient stock for {product.name}.")
                        price = product.price
                        discount_price = product.discount_price

                    final_price = discount_price if discount_price else price
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
                order.save(update_fields=["total_cost"])

                messages.success(request, f"Order {order.order_id} created successfully.")
                return redirect("order_list")

        except Exception as e:
            messages.error(request, str(e))
            return redirect("add_order")
        

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

            "status_choices": STATUS.choices,
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
    login_url = "admin_login"

    def get_order(self, id):
        return get_object_or_404(
            Order.objects.select_related("customer").prefetch_related(
                "order_items", "order_items__product", "order_items__variant"
            ),
            id=id,
        )

    def get(self, request, id):
        order = self.get_order(id)

        products = Product.objects.prefetch_related("variants").order_by("name")
        assignable_users = CustomUser.objects.filter(
            user_type__in=[USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN, USER_TYPE.STAFF]
        ).order_by("username")

        existing_items_data = []
        for item in order.order_items.all():
            existing_items_data.append({
                "id": item.id,
                "product_id": item.product_id,
                "variant_id": item.variant_id,
                "product_name": item.product_name,
                "variant_label": ", ".join(
                    f"{k}: {v}" for k, v in (item.variant.attributes.items() if item.variant else {}.items())
                ) or None,
                "quantity": item.quantity,
                "unit_price": str(item.discount_price or item.price or 0),
            })

        orders = Order.objects.all().order_by("-created_at")
        dashboard_view = DashboardView()

        context = {
            "order": order,
            "is_update": True,
            "products": products,
            "categories": Category.objects.order_by("name"),
            "payment_types": PAYMENT_TYPE.choices,
            "delivery_types": DELIVERY_TYPE.choices,
            "status_choices": STATUS.choices,
            "variants_by_product_json": pyjson.dumps(build_variants_by_product(products)),
            "assignable_users": assignable_users,
            "existing_items_json": pyjson.dumps(existing_items_data),

            # Needed because the inherited base template references these
            "status_amounts": dashboard_view.get_status_amounts(orders),
            "today_order_count": dashboard_view.get_today_order_count(orders),
            "new_orders_count": dashboard_view.new_orders_count(orders),
            "total_orders": orders.count(),
            "new_order_request_count": dashboard_view.new_order_request_count(),
        }

        if request.htmx:
            return render(request, "db_order/partial/partial_order_detail.html", context)
        return render(request, "db_order/order_detail.html", context)



class OrderUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)

        try:
            with transaction.atomic():
                data = request.POST

                customer = order.customer
                if customer:
                    customer.company = data.get("company", customer.company)
                    customer.name = data.get("name", customer.name).strip() or customer.name
                    customer.email = data.get("email") or customer.email
                    customer.phone = data.get("phone", customer.phone).strip() or customer.phone
                    customer.second_phone = data.get("second_phone") or customer.second_phone
                    customer.source = data.get("source", customer.source)
                    customer.save()

                work_assign_id = data.get("work_assign") or None
                assigned_user = None
                if work_assign_id:
                    assigned_user = CustomUser.objects.filter(id=work_assign_id).first()

                order.shipping_address = data.get("shipping_address", order.shipping_address).strip()
                order.note = data.get("note", order.note)
                order.special_instructions = data.get("special_instructions") or None
                order.work_assign = assigned_user.username if assigned_user else None
                order.payment_type = data.get("payment_type", order.payment_type)
                order.delivery_type = data.get("delivery_type", order.delivery_type)
                order.status = data.get("status", order.status)
                order.is_urgent = data.get("is_urgent") == "on"
                order.order_created_date = data.get("order_created_date") or None
                order.delivery_date = data.get("delivery_date") or None
                order.shipping_total = parse_decimal(data.get("shipping_total"))
                order.advance_amount = parse_decimal(data.get("advance_amount"))

                delete_design_file = data.get("delete_design_file")
                if delete_design_file:
                    if order.design_file:
                        order.design_file.delete(save=False)
                    order.design_file = None

                new_design_file = request.FILES.get("design_file")
                if new_design_file:
                    order.design_file = new_design_file

                try:
                    items = json.loads(data.get("items", "[]"))
                except json.JSONDecodeError:
                    messages.error(request, "Invalid product data.")
                    return redirect("order_detail", id=pk)

                if not items:
                    messages.error(request, "Please add at least one product.")
                    return redirect("order_detail", id=pk)

                order.order_items.all().delete()

                grand_total = order.shipping_total

                for item in items:
                    product = get_object_or_404(Product, id=item["product_id"])
                    variant = None
                    if item.get("variant_id"):
                        variant = get_object_or_404(ProductVariant, id=item["variant_id"], product=product)

                    quantity = max(int(item.get("quantity", 1)), 1)
                    price = variant.price if variant else product.price
                    discount_price = variant.discount_price if variant else product.discount_price
                    final_price = discount_price if discount_price else price
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
                order.save()

                messages.success(request, f"Order {order.order_id} updated successfully.")
                return redirect("order_detail", id=pk)

        except Exception as e:
            messages.error(request, str(e))
            return redirect("order_detail", id=pk)

class OrderInvoiceView(View):
    def get_order(self, id):
        return get_object_or_404(Order, id=id)

    def get(self, request, id):
        print("id: ", id)
        order = self.get_order(id)
        if order:
            return render(request, "db_order/invoice.html", {"order": order})
        return redirect(request.META.get("HTTP_REFERER"))

class OrderStatusUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        new_status = request.POST.get("status")

        valid_statuses = [c[0] for c in STATUS.choices]
        if new_status not in valid_statuses:
            messages.error(request, "Invalid status selected.")
        else:
            order.status = new_status
            order.save(update_fields=["status"])
            messages.success(
                request,
                f"Order #{order.order_id} status updated to {order.get_status_display()}."
            )

        if request.htmx:
            order_view = OrderView()
            (
                orders,
                paginator,
                per_page,
                page_number,
                products,
            ) = order_view.get_order_queryset(request)

            context = {
                "orders": orders,
                "paginator": paginator,
                "per_page": per_page,
                "page_number": page_number,
                "order_count": order_view.status_wise_order_count(),
                "current_status": request.GET.get("status", "all"),
                "current_search": request.GET.get("q", ""),
                "current_product_slug": request.GET.get("product", ""),
                "start_date": request.GET.get("start_date", ""),
                "end_date": request.GET.get("end_date", ""),
                "products": products,
                "status_choices": STATUS.choices,
            }
            return render(request, "db_order/partial/partial_order_list.html", context)

        return redirect("order_list")


# Order Request section
def create_order_from_request(order_request):
    if order_request.status not in [ORDER_REQUEST_STATUS.PENDING, ORDER_REQUEST_STATUS.APPROVED]:
        raise Exception("Only pending or approved requests can be converted.")

    if order_request.converted_order:
        raise Exception("This request has already been converted.")

    with transaction.atomic():
        order = Order.objects.create(
            customer=order_request.customer,
            shipping_address=order_request.shipping_address,
            note=order_request.note,
            special_instructions=order_request.special_instructions,
            work_assign=order_request.work_assign.username if order_request.work_assign else None,
            payment_type=order_request.payment_type,
            delivery_type=order_request.delivery_type,
            shipping_total=order_request.shipping_total,
            advance_amount=order_request.advance_amount,
            total_cost=order_request.total_cost,
            payment_status=PAYMENT_STATUS.Unpaid,
            status=STATUS.NEW,
            is_urgent=order_request.is_urgent,
            order_created_date=order_request.order_created_date,
            design_file=order_request.design_file,
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
                snapshot=item.snapshot,
            )

        order_request.status = ORDER_REQUEST_STATUS.CONVERTED
        order_request.work_status = ORDER_REQUEST_WORK_STATUS.DONE
        order_request.converted_order = order
        order_request.converted_at = timezone.now()
        order_request.save(update_fields=["status", "work_status", "converted_order", "converted_at"])

    return order

class AddOrderRequestView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_order_request/add_order_request.html"

    def get(self, request, pk=None):
        order_request = None
        existing_items_data = []

        if pk:
            order_request = get_object_or_404(
                OrderRequest.objects.select_related("customer", "work_assign").prefetch_related(
                    "request_items", "request_items__product", "request_items__variant"
                ),
                pk=pk,
            )
            for item in order_request.request_items.all():
                existing_items_data.append({
                    "id": item.id,
                    "product_id": item.product_id,
                    "variant_id": item.variant_id,
                    "product_name": item.product_name,
                    "variant_label": ", ".join(
                        f"{k}: {v}" for k, v in (item.variant.attributes.items() if item.variant else {}.items())
                    ) or None,
                    "quantity": item.quantity,
                    "unit_price": str(item.discount_price or item.price or 0),
                })

        products = Product.objects.prefetch_related("variants", "category").order_by("name")
        assignable_users = CustomUser.objects.filter(
            user_type__in=[USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN, USER_TYPE.STAFF]
        ).order_by("username")
        context = {
            "order_request": order_request,
            "is_update": bool(order_request),
            "products": products,
            "categories": Category.objects.all().order_by("name"),
            "payment_types": PAYMENT_TYPE.choices,
            "delivery_types": DELIVERY_TYPE.choices,
            "status_choices": ORDER_REQUEST_STATUS.choices,
            "variants_by_product_json": pyjson.dumps(build_variants_by_product(products)),
            "assignable_users": assignable_users,
            "existing_items_json": pyjson.dumps(existing_items_data),
        }
        return render(request, self.template_name, context)

    def post(self, request, pk=None):
        try:
            with transaction.atomic():
                data = request.POST

                if pk:
                    order_request = get_object_or_404(OrderRequest, pk=pk)
                    customer = order_request.customer
                else:
                    order_request = None
                    customer = None

                company = data.get("company", "").strip()
                name = data.get("name", "").strip()
                email = data.get("email", "").strip()
                phone = data.get("phone", "").strip()
                second_phone = data.get("second_phone", "").strip()
                source = data.get("source", "Others").strip()

                if not name:
                    messages.error(request, "Customer name is required.")
                    return redirect("add_order_request") if not pk else redirect("edit_order_request", pk=pk)
                if not phone:
                    messages.error(request, "Phone number is required.")
                    return redirect("add_order_request") if not pk else redirect("edit_order_request", pk=pk)

                if customer:
                    customer.company = company or None
                    customer.name = name
                    customer.phone = phone
                    customer.second_phone = second_phone or None
                    customer.email = email or None
                    customer.source = source or "Others"
                    customer.save()
                else:
                    customer = Customer.objects.create(
                        company=company or None,
                        name=name,
                        phone=phone,
                        second_phone=second_phone or None,
                        email=email or None,
                        source=source or "Others",
                    )

                shipping_address = data.get("shipping_address", "").strip()
                note = data.get("note", "").strip()
                special_instructions = data.get("special_instructions", "").strip()

                work_assign_id = data.get("work_assign") or None
                assigned_user = None
                if work_assign_id:
                    assigned_user = CustomUser.objects.filter(id=work_assign_id).first()

                payment_type = data.get("payment_type", PAYMENT_TYPE.COD)
                delivery_type = data.get("delivery_type", DELIVERY_TYPE.HOME_DELIVERY)
                is_urgent = data.get("is_urgent") == "on"

                order_created_date = data.get("order_created_date") or None
                delivery_date = data.get("delivery_date") or None

                shipping_total = parse_decimal(data.get("shipping_total"))
                advance_amount = parse_decimal(data.get("advance_amount"))

                design_file = request.FILES.get("design_file")

                try:
                    items = json.loads(data.get("items", "[]"))
                except json.JSONDecodeError:
                    messages.error(request, "Invalid product data.")
                    return redirect("add_order_request") if not pk else redirect("edit_order_request", pk=pk)

                if not items:
                    messages.error(request, "Please add at least one product.")
                    return redirect("add_order_request") if not pk else redirect("edit_order_request", pk=pk)

                if order_request:
                    order_request.shipping_address = shipping_address
                    order_request.note = note
                    order_request.special_instructions = special_instructions or None
                    order_request.work_assign = assigned_user
                    order_request.payment_type = payment_type
                    order_request.delivery_type = delivery_type
                    order_request.shipping_total = shipping_total
                    order_request.advance_amount = advance_amount
                    order_request.is_urgent = is_urgent
                    order_request.order_created_date = order_created_date
                    order_request.delivery_date = delivery_date

                    delete_design_file = data.get("delete_design_file")
                    if delete_design_file:
                        if order_request.design_file:
                            order_request.design_file.delete(save=False)
                        order_request.design_file = None
                    if design_file:
                        order_request.design_file = design_file

                    order_request.request_items.all().delete()
                else:
                    order_request = OrderRequest.objects.create(
                        customer=customer,
                        shipping_address=shipping_address,
                        note=note,
                        special_instructions=special_instructions or None,
                        work_assign=assigned_user,
                        payment_type=payment_type,
                        delivery_type=delivery_type,
                        shipping_total=shipping_total,
                        advance_amount=advance_amount,
                        status=ORDER_REQUEST_STATUS.PENDING,
                        is_urgent=is_urgent,
                        order_created_date=order_created_date,
                        design_file=design_file,
                        delivery_date=delivery_date,
                    )

                grand_total = shipping_total

                for item in items:
                    product = Product.objects.get(id=item["product_id"])
                    variant = None
                    if item.get("variant_id"):
                        variant = ProductVariant.objects.get(id=item["variant_id"], product=product)

                    quantity = int(item.get("quantity", 1))

                    price = variant.price if variant else product.price
                    discount_price = variant.discount_price if variant else product.discount_price
                    final_price = discount_price if discount_price else price
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
                order_request.save()

                messages.success(request, "Order Request saved successfully.")
                return redirect("order_request_detail", id=order_request.pk)

        except Exception as e:
            messages.error(request, str(e))
            return redirect("add_order_request") if not pk else redirect("edit_order_request", pk=pk)
               

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

            "status_choices": ORDER_REQUEST_STATUS.choices,
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
                "work_assign",
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
            "work_status_choices": ORDER_REQUEST_WORK_STATUS.choices,
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
        order_request = get_object_or_404(OrderRequest, pk=pk)

        try:
            order = create_order_from_request(order_request)
            messages.success(
                request,
                f"Order Request approved successfully. Order #{order.order_id} created."
            )
        except Exception as e:
            messages.error(request, str(e))

        return redirect("order_request_detail", id=pk)


class RejectOrderRequestView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        order_request = get_object_or_404(OrderRequest, pk=pk)

        if order_request.status not in [ORDER_REQUEST_STATUS.PENDING, ORDER_REQUEST_STATUS.APPROVED]:
            messages.error(request, "Only pending requests can be rejected.")
            return redirect("order_request_detail", id=pk)

        order_request.status = ORDER_REQUEST_STATUS.CANCELLED
        order_request.save(update_fields=["status"])

        messages.success(request, "Order Request cancelled successfully.")
        return redirect("order_request_detail", id=pk)


class UpdateOrderRequestWorkStatusView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        order_request = get_object_or_404(OrderRequest, pk=pk)
        work_status = request.POST.get("work_status")

        valid = [x[0] for x in ORDER_REQUEST_WORK_STATUS.choices]
        if work_status not in valid:
            messages.error(request, "Invalid work status.")
            return redirect("order_request_detail", id=pk)

        order_request.work_status = work_status
        order_request.save()

        messages.success(request, "Work status updated.")
        return redirect("order_request_detail", id=pk)  
    

class OrderRequestStatusUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        order_request = get_object_or_404(OrderRequest, pk=pk)
        new_status = request.POST.get("status")

        valid_statuses = [c[0] for c in ORDER_REQUEST_STATUS.choices]

        if new_status not in valid_statuses:
            messages.error(request, "Invalid status selected.")

        elif order_request.status == ORDER_REQUEST_STATUS.CONVERTED:
            messages.error(request, "Converted requests cannot change status.")

        elif new_status == ORDER_REQUEST_STATUS.CONVERTED:
            # Route through the existing conversion logic instead of a raw status set
            try:
                order = create_order_from_request(order_request)
                messages.success(
                    request,
                    f"Order Request approved. Order #{order.order_id} created."
                )
            except Exception as e:
                messages.error(request, str(e))

        else:
            order_request.status = new_status
            order_request.save(update_fields=["status"])
            messages.success(
                request,
                f"Order Request #{order_request.id} status updated to {order_request.get_status_display()}."
            )

        if request.htmx:
            request_view = OrderRequestListView()
            (
                requests_qs,
                paginator,
                per_page,
                page_number,
            ) = request_view.get_request_queryset(request)

            context = {
                "requests": requests_qs,
                "paginator": paginator,
                "per_page": per_page,
                "page_number": page_number,
                "request_count": request_view.status_wise_request_count(),
                "current_status": request.GET.get("status", "all"),
                "current_search": request.GET.get("q", ""),
                "start_date": request.GET.get("start_date", ""),
                "end_date": request.GET.get("end_date", ""),
                "status_choices": ORDER_REQUEST_STATUS.choices,
            }
            return render(request, "db_order_request/partial/partial_order_request_list.html", context)

        return redirect("order_request_list")
    
    
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
