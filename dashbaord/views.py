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


# Models
from order.models import Order
from product.models import Product, Category, ProductImage, ProductVideo, Attribute, AttributeValue, ProductVariant
from authentication.models import CustomUser
from site_app.models import DeliveryOption

# Forms
from product.forms import ProductForm, ProductImageForm, ProductVideoForm
from django.forms import modelformset_factory

# Utilities
from order.utils import SteadFastParcelAPI

# Choices
from pencilwoodbd.choices import USER_TYPE, STATUS, CATEGORY_PRODUCT_STATUS, DELIVERY_TYPE


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
        context = {
            "orders": orders[:10],
            "total_order_amount": self.get_total_order_amount(orders),
            "total_orders": orders.count(),
            "today_order_count": self.get_today_order_count(orders),
            "today_sales_amount": self.get_today_sales_amount(orders),
            "new_orders_count": self.new_orders_count(orders),
            "status_amounts": self.get_status_amounts(orders),
        }
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
        return render(request, "db_product/product_list.html", {"products": products})


@login_required(login_url="admin_login")
def add_product(request):
    ImageFormSet = modelformset_factory(ProductImage, form=ProductImageForm, extra=3, can_delete=True)
    VideoFormSet = modelformset_factory(ProductVideo, form=ProductVideoForm, extra=1, can_delete=True)

    attributes = Attribute.objects.prefetch_related("attributevalue_set").all()  # for variant selection

    if request.method == "POST":
        product_form = ProductForm(request.POST)
        image_formset = ImageFormSet(request.POST, request.FILES, queryset=ProductImage.objects.none())
        video_formset = VideoFormSet(request.POST, request.FILES, queryset=ProductVideo.objects.none())

        variant_data = request.POST.getlist("variants")  # expects JSON or structured variant input

        if product_form.is_valid() and image_formset.is_valid() and video_formset.is_valid():
            try:
                with transaction.atomic():
                    product = product_form.save()

                    # Images
                    for img_form in image_formset.cleaned_data:
                        if img_form and not img_form.get("DELETE", False):
                            ProductImage.objects.create(
                                product=product,
                                image=img_form.get("image"),
                                role=img_form.get("role","gallery"),
                                position=img_form.get("position",0)
                            )

                    # Videos
                    for vid_form in video_formset.cleaned_data:
                        if vid_form and vid_form.get("video"):
                            ProductVideo.objects.create(
                                product=product,
                                video=vid_form.get("video")
                            )

                    # Variants (optional)
                    if variant_data:
                        variant_fields = [f.name for f in ProductVariant._meta.fields 
                                        if f.name not in ["id", "product", "sku", "created_at", "updated_at", "inventory_quantity"]]
                        for variant_json in variant_data:
                            attr_values = json.loads(variant_json)  # e.g., {"size":1, "color":4}
                            variant_kwargs = {k: v for k, v in attr_values.items() if k in variant_fields}
                            ProductVariant.objects.create(
                                product=product,
                                sku=f"{product.slug}-{random.randint(1000,9999)}",
                                price=product.price,
                                inventory_quantity=product.inventory_quantity,  # initialize same as product
                                **variant_kwargs
                            )
                    # Sync product inventory
                    product.inventory_quantity = sum(v.inventory_quantity for v in product.variants.filter(is_active=True))
                    product.save(update_fields=["inventory_quantity"])

                    messages.success(request, "Product added successfully!")
                    return redirect("product_list")
            except Exception as e:
                messages.error(request, f"Error saving product: {e}")
        else:
            messages.error(request, "Please correct the errors below")
    else:
        product_form = ProductForm()
        image_formset = ImageFormSet(queryset=ProductImage.objects.none())
        video_formset = VideoFormSet(queryset=ProductVideo.objects.none())

    return render(request, "db_product/add_product.html", {
        "product_form": product_form,
        "image_formset": image_formset,
        "video_formset": video_formset,
        "attributes": attributes,
    })


@login_required(login_url="admin_login")
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    variants = ProductVariant.objects.filter(product=product)
    ImageFormSet = modelformset_factory(ProductImage, form=ProductImageForm, extra=0, can_delete=True)
    VideoFormSet = modelformset_factory(ProductVideo, form=ProductVideoForm, extra=0, can_delete=True)

    attributes = Attribute.objects.prefetch_related("attributevalue_set").all()

    if request.method == "POST":
        product_form = ProductForm(request.POST, instance=product)
        image_formset = ImageFormSet(request.POST, request.FILES, queryset=ProductImage.objects.filter(product=product))
        video_formset = VideoFormSet(request.POST, request.FILES, queryset=ProductVideo.objects.filter(product=product))
        variant_data = request.POST.getlist("variants")  # same as add

        if product_form.is_valid() and image_formset.is_valid() and video_formset.is_valid():
            try:
                with transaction.atomic():
                    product_form.save()

                    # Images
                    for form in image_formset:
                        if form.cleaned_data.get("DELETE") and form.instance.pk:
                            form.instance.delete()
                        else:
                            img = form.save(commit=False)
                            img.product = product
                            img.save()

                    # Videos
                    for form in video_formset:
                        if form.cleaned_data.get("DELETE") and form.instance.pk:
                            form.instance.delete()
                        else:
                            vid = form.save(commit=False)
                            vid.product = product
                            vid.save()

                    # Variants
                    existing_variants = {v.id: v for v in variants}
                    for variant_json in variant_data:
                        v_data = json.loads(variant_json)
                        v_id = v_data.get("id")
                        if v_id and v_id in existing_variants:
                            variant = existing_variants[v_id]
                            variant_fields = [f.name for f in ProductVariant._meta.fields 
                                            if f.name not in ["id", "product", "sku", "created_at", "updated_at", "inventory_quantity"]]
                            # update all fields dynamically
                            for field in variant_fields:
                                if field in v_data:
                                    setattr(variant, field, v_data[field])
                            variant.price = v_data.get("price", variant.price)
                            variant.save()
                        else:
                            # optional attributes handled dynamically
                            variant_fields = [f.name for f in ProductVariant._meta.fields 
                                            if f.name not in ["id", "product", "sku", "created_at", "updated_at", "inventory_quantity"]]

                            attrs = {k: v for k, v in v_data.items() if k in variant_fields}
                            ProductVariant.objects.create(
                                product=product,
                                sku=f"{product.slug}-{random.randint(1000,9999)}",
                                price=v_data.get("price", product.price),
                                **attrs
                            )

                    # Sync product inventory BEFORE returning
                    product.inventory_quantity = sum(
                        v.inventory_quantity for v in product.variants.filter(is_active=True)
                    )
                    product.save(update_fields=["inventory_quantity"])

                    messages.success(request, "Product updated successfully")
                    return redirect("product_list")

            except Exception as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Please fix the errors below")
    else:
        product_form = ProductForm(instance=product)
        image_formset = ImageFormSet(queryset=ProductImage.objects.filter(product=product))
        video_formset = VideoFormSet(queryset=ProductVideo.objects.filter(product=product))

    return render(request, "db_product/add_product.html", {
        "product_form": product_form,
        "image_formset": image_formset,
        "video_formset": video_formset,
        "is_update": True,
        "product": product,
        "variants": variants,
        "attributes": attributes,
    })


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
class OrderView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def status_wise_order_count(self):
        qs = Order.objects.values("status").annotate(total=Count("id"))
        order_count = {status: 0 for status, _ in STATUS.choices}
        for row in qs:
            order_count[row["status"]] = row["total"]
        order_count["all"] = sum(order_count.values())
        return order_count

    def get_order_queryset(self, request):
        order_status = request.GET.get("status")
        search = request.GET.get("q", "")
        orders = Order.objects.all().order_by("-created_at")
        
        product_slug = request.GET.get("product")
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        if order_status and order_status in STATUS.values:
            orders = orders.filter(status=order_status)
        
        if product_slug:
                orders = orders.filter(
                    Q(order_items__variant__product__slug=product_slug) 
                    | Q(order_items__product__slug=product_slug)                     
                ).distinct()
                    
        if start_date and end_date:
            orders = orders.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        elif start_date:
            orders = orders.filter(created_at__date=start_date)
        elif end_date:
            orders = orders.filter(created_at__date__lte=end_date)

        if search:
            orders = orders.filter(
                Q(order_id__icontains=search)
                | Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(status__icontains=search)
                | Q(payment_status__icontains=search)
                | Q(delivery_type__icontains=search)
                | Q(shipping_address__icontains=search)
            )

        page_number = request.GET.get("page", 1)
        per_page = int(request.GET.get("per_page", 10))
        paginator = Paginator(orders, per_page)
        orders = paginator.get_page(page_number)

        products = Product.objects.all().distinct()
        return orders, paginator, per_page, page_number, products

    def permission_denied(self, request):
        if not request.user.is_authenticated:
            return redirect("product_landing_page")
        elif request.user.user_type not in [
            USER_TYPE.ADMIN,
            USER_TYPE.STAFF,
            USER_TYPE.SUPER_ADMIN,
        ]:
            return redirect("product_landing_page")

    def get(self, request):
        orders, paginator, per_page, page_number, products = self.get_order_queryset(request)
        context = {
            "orders": orders,
            "paginator": paginator,
            "per_page": per_page,
            "page_number": page_number,
            "order_count": self.status_wise_order_count(),

            "current_status": request.GET.get("status", "all"),
            "current_search": request.GET.get("q", ""),
            "current_product_slug":  request.GET.get("product", ""),
            "start_date":  request.GET.get("start_date", ""),
            "end_date":  request.GET.get("end_date", ""),

            "products": products,
        }
        if request.htmx:
            return render(request, "db_order/partial/partial_order_list.html", context)
        return render(request, "db_order/order_list.html", context)

    def post(self, request):
        if not request.user.is_authenticated:
            return redirect("product_landing_page")
        elif request.user.user_type not in [
            USER_TYPE.ADMIN,
            USER_TYPE.STAFF,
            USER_TYPE.SUPER_ADMIN,
        ]:
            return redirect("product_landing_page")

        try:
            with transaction.atomic():
                data = request.POST

                if data.get("order_id"):
                    order = Order.objects.get(id=data.get("order_id"))
                    order.name = data.get("order_title")
                    order.description = data.get("order_description")
                    order.save()
                    return JsonResponse(
                        {"status": True, "message": "Order updated successfully"},
                        status=HTTPStatus.OK,
                    )

                if data.get("order_title") == "":
                    return JsonResponse(
                        {"status": False, "message": "Order title is required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                if data.get("order_description") == "":
                    return JsonResponse(
                        {"status": False, "message": "Order description is required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                Order.objects.create(
                    name=data.get("order_title"),
                    description=data.get("order_description"),
                    status=STATUS.Pending,
                )
                return JsonResponse(
                    {"status": True, "message": "Order added successfully"},
                    status=HTTPStatus.CREATED,
                )
        except Exception as e:
            print("Exception", e)
            return JsonResponse(
                {"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST
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
                print("steadfast_response: ", steadfast_response)
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
