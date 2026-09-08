from http import HTTPStatus
import json
import json as pyjson
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import DeleteView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse_lazy

from pencilwoodbd.extra_module import parse_decimal
from pencilwoodbd.choices import (
    USER_TYPE, STATUS, DELIVERY_TYPE, ORDER_REQUEST_STATUS, PAYMENT_TYPE,
    PAYMENT_STATUS, ORDER_REQUEST_WORK_STATUS, ORDER_SOURCE,
)

# Models
from .models import Order, OrderRequest, OrderItem, OrderRequestItem, TelegramBotConfig
from product.models import Product, ProductVariant, Category
from authentication.models import CustomUser, Customer, OrderTrackRecord
from site_app.models import DeliveryOption

# Utilities
from .utils import PathaoParcelAPI, SteadFastParcelAPI

# Reuses stat-calculation helpers from the main dashboard homepage view
from dashbaord.views import DashboardView


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


def get_assignable_users():
    return CustomUser.objects.filter(
        user_type__in=[
            USER_TYPE.STAFF,
            USER_TYPE.ADMIN,
            USER_TYPE.SUPER_ADMIN,
        ]
    ).order_by("username")


class AddOrderView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_order/add_order.html"

    def get(self, request):
        products = Product.objects.prefetch_related("variants").order_by("name")
        assignable_users = get_assignable_users()
        context = {
            "products": products,
            "categories": Category.objects.order_by("name"),
            "payment_types": PAYMENT_TYPE.choices,
            "delivery_types": DELIVERY_TYPE.choices,
            "status_choices": STATUS.choices,
            "variants_by_product_json": pyjson.dumps(build_variants_by_product(products)),
            "assignable_users": assignable_users,
            "source_choices": ORDER_SOURCE.choices,
            "existing_items_json": "[]",
            "is_update": False,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        try:
            with transaction.atomic():
                data = request.POST

                company = data.get("company", "").strip()
                name = data.get("name", "").strip()
                email = data.get("email", "").strip()
                phone = data.get("phone", "").strip()
                second_phone = data.get("second_phone", "").strip()

                valid_sources = [c[0] for c in ORDER_SOURCE.choices]
                source = data.get("source", ORDER_SOURCE.OTHERS).strip()
                if source not in valid_sources:
                    source = ORDER_SOURCE.OTHERS

                if not name:
                    if is_ajax:
                        return JsonResponse({"status": False, "message": "Customer name is required."}, status=400)
                    messages.error(request, "Customer name is required.")
                    return redirect("add_order")

                if not phone:
                    if is_ajax:
                        return JsonResponse({"status": False, "message": "Phone number is required."}, status=400)
                    messages.error(request, "Phone number is required.")
                    return redirect("add_order")

                customer, created = Customer.objects.get_or_create(
                    phone=phone,
                    defaults={
                        "company": company or None,
                        "name": name,
                        "second_phone": second_phone or None,
                        "email": email or None,
                    }
                )
                if not created:
                    customer.company = company or customer.company
                    customer.name = name or customer.name
                    customer.second_phone = second_phone or customer.second_phone
                    customer.email = email or customer.email
                    customer.save()

                shipping_address = data.get("shipping_address", "").strip()
                note = data.get("note", "").strip()
                special_instructions = data.get("special_instructions", "").strip()

                work_assign_id = data.get("work_assign") or None
                assigned_user = None

                if work_assign_id:
                    assigned_user = get_assignable_users().filter(
                        id=work_assign_id
                    ).first()

                payment_type = data.get("payment_type", PAYMENT_TYPE.COD)
                delivery_type = data.get("delivery_type", DELIVERY_TYPE.HOME_DELIVERY)
                status = data.get("status", STATUS.NEW)
                is_urgent = data.get("is_urgent") == "on"

                order_created_date = data.get("order_created_date") or None
                delivery_date = data.get("delivery_date") or None

                shipping_total = parse_decimal(data.get("shipping_total"))
                advance_amount = parse_decimal(data.get("advance_amount"))
                extra_discount = parse_decimal(data.get("extra_discount"))

                design_file = request.FILES.get("design_file")

                try:
                    items = json.loads(data.get("items", "[]"))
                except json.JSONDecodeError:
                    if is_ajax:
                        return JsonResponse({"status": False, "message": "Invalid product data."}, status=400)
                    messages.error(request, "Invalid product data.")
                    return redirect("add_order")

                if not items:
                    if is_ajax:
                        return JsonResponse({"status": False, "message": "Please add at least one product."}, status=400)
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
                    extra_discount=extra_discount,
                    payment_status=PAYMENT_STATUS.Unpaid,
                    status=status,
                    is_urgent=is_urgent,
                    order_created_date=order_created_date,
                    delivery_date=delivery_date,
                    design_file=design_file,
                    source=source,
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
                        default_price = variant.price
                        default_discount_price = variant.discount_price
                    else:
                        if product.inventory_quantity < quantity:
                            raise Exception(f"Insufficient stock for {product.name}.")
                        default_price = product.price
                        default_discount_price = product.discount_price

                    manually_edited = bool(item.get("price_manually_edited"))
                    if manually_edited and item.get("unit_price") is not None:
                        manual_unit_price = parse_decimal(item.get("unit_price"))
                        price = manual_unit_price
                        discount_price = manual_unit_price
                        final_price = manual_unit_price
                    else:
                        price = default_price
                        discount_price = default_discount_price
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

                grand_total -= extra_discount
                if grand_total < 0:
                    grand_total = Decimal("0")

                order.total_cost = grand_total
                order.save(update_fields=["total_cost"])


                if is_ajax:
                    return JsonResponse({
                        "status": True,
                        "message": f"Order {order.order_id} created successfully."
                    }, status=201)
                else:
                    messages.success(request, f"Order {order.order_id} created successfully.")
                    return redirect("order_detail", id=order.id)
        except Exception as e:
            if is_ajax:
                return JsonResponse({"status": False, "message": str(e)}, status=400)
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

        order_count["all"] = sum(
            v for k, v in order_count.items()
        )

        order_count["urgent"] = Order.objects.filter(is_urgent=True).exclude(
            status__in=[STATUS.DELIVERED, STATUS.CANCELLED, STATUS.RETURNED, STATUS.REFUNDED]
        ).count()

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

        valid_status = {status for status, _ in STATUS.choices}

        if order_status in valid_status:
            orders = orders.filter(status=order_status)

        if product_slug:
            orders = orders.filter(
                Q(order_items__product__slug=product_slug)
                | Q(order_items__variant__product__slug=product_slug)
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
                | Q(shipping_address__icontains=search)
                | Q(status__iexact=search)
                | Q(payment_status__iexact=search)
                | Q(delivery_type__iexact=search)
            ).distinct()

        if request.GET.get("urgent") == "1":
            orders = orders.filter(is_urgent=True)

        try:
            per_page = int(request.GET.get("per_page", 10))
        except (TypeError, ValueError):
            per_page = 10

        page_number = request.GET.get("page", 1)

        paginator = Paginator(orders, per_page)
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
            "current_status": request.GET.get("status", "all"),
            "current_search": request.GET.get("q", ""),
            "current_product_slug": request.GET.get("product", ""),
            "start_date": request.GET.get("start_date", ""),
            "end_date": request.GET.get("end_date", ""),
            "products": products,
            "status_choices": STATUS.choices,
            "delivery_types": DELIVERY_TYPE.choices,
            "payment_types": PAYMENT_TYPE.choices,
            "staff_list": get_assignable_users(),
        }

        if request.htmx:
            return render(request, "db_order/partial/partial_order_list.html", context)

        return render(request, "db_order/order_list.html", context)    


def _get_order_block_status(order):
    from authentication.models import OrderTrackRecord, BlockedIdentity

    track_record = OrderTrackRecord.objects.filter(order=order).order_by("-created_at").first()
    phone = order.customer.phone if order.customer else None

    query = Q()
    if track_record and track_record.ip_address:
        query |= Q(ip_address=track_record.ip_address)
    if track_record and track_record.device_hash:
        query |= Q(device_hash=track_record.device_hash)
    if phone:
        query |= Q(phone=phone)

    if not query:
        return None

    return BlockedIdentity.objects.filter(query, is_active=True).first()


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
        assignable_users = get_assignable_users()

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
            "source_choices": ORDER_SOURCE.choices,
            "staff_list": CustomUser.objects.filter(
                user_type__in=[USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]
            ),
            "status_amounts": dashboard_view.get_status_amounts(orders),
            "today_order_count": dashboard_view.get_today_order_count(orders),
            "new_orders_count": dashboard_view.new_orders_count(orders),
            "total_orders": orders.count(),
            "new_order_request_count": dashboard_view.new_order_request_count(),
            "track_record": OrderTrackRecord.objects.filter(order=order).order_by("-created_at").first(),
            "identity_blocked": _get_order_block_status(order),
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
                    customer.save()

                valid_sources = [c[0] for c in ORDER_SOURCE.choices]
                new_source = data.get("source", order.source)
                if new_source in valid_sources:
                    order.source = new_source

                work_assign_id = data.get("work_assign") or None
                assigned_user = None

                if work_assign_id:
                    assigned_user = get_assignable_users().filter(
                        id=work_assign_id
                    ).first()

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
                order.extra_discount = parse_decimal(data.get("extra_discount"))

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
                    default_price = variant.price if variant else product.price
                    default_discount_price = variant.discount_price if variant else product.discount_price

                    manually_edited = bool(item.get("price_manually_edited"))
                    if manually_edited and item.get("unit_price") is not None:
                        manual_unit_price = parse_decimal(item.get("unit_price"))
                        price = manual_unit_price
                        discount_price = manual_unit_price
                        final_price = manual_unit_price
                    else:
                        price = default_price
                        discount_price = default_discount_price
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

                grand_total -= order.extra_discount
                if grand_total < 0:
                    grand_total = Decimal("0")

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

    # def post(self, request, pk):
    #     order = get_object_or_404(Order, pk=pk)
    #     new_status = request.POST.get("status")

    #     valid_statuses = [c[0] for c in STATUS.choices]
    #     if new_status not in valid_statuses:
    #         messages.error(request, "Invalid status selected.")
    #     else:
    #         order.status = new_status
    #         order.save(update_fields=["status"])
    #         messages.success(
    #             request,
    #             f"Order #{order.order_id} status updated to {order.get_status_display()}."
    #         )

    #     if request.htmx:
    #         order_view = OrderView()
    #         (
    #             orders,
    #             paginator,
    #             per_page,
    #             page_number,
    #             products,
    #         ) = order_view.get_order_queryset(request)

    #         context = {
    #             "orders": orders,
    #             "paginator": paginator,
    #             "per_page": per_page,
    #             "page_number": page_number,
    #             "order_count": order_view.status_wise_order_count(),
    #             "current_status": request.GET.get("status", "all"),
    #             "current_search": request.GET.get("q", ""),
    #             "current_product_slug": request.GET.get("product", ""),
    #             "start_date": request.GET.get("start_date", ""),
    #             "end_date": request.GET.get("end_date", ""),
    #             "products": products,
    #             "status_choices": STATUS.choices,
    #         }
    #         return render(request, "db_order/partial/partial_order_list.html", context)

    #     return redirect("order_list")

    def post(self, request, pk) -> JsonResponse:
        try:
            order = get_object_or_404(Order, pk=pk)
            new_status = request.POST.get("status")

            valid_statuses = [c[0] for c in STATUS.choices]
            if new_status not in valid_statuses:
                return JsonResponse({"success": False, "message": "Invalid status selected"})
            else:
                order.status = new_status
                update_fields = ["status"]
                if new_status == STATUS.DELIVERED and not order.delivered_at:
                    order.delivered_at = timezone.now()
                    update_fields.append("delivered_at")
                order.save(update_fields=update_fields)
            return JsonResponse({"success": True, "message": f"Order #{order.order_id} status updated to {order.get_status_display()}."})
        except Exception as e:
            return JsonResponse({"success": False, "message": f"{e}"})

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
            delivery_date=order_request.delivery_date,  # ADD
            design_file=order_request.design_file,
            source=order_request.source,
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
        assignable_users = get_assignable_users()
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
            "source_choices": ORDER_SOURCE.choices,
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

                valid_sources = [c[0] for c in ORDER_SOURCE.choices]
                source = data.get("source", ORDER_SOURCE.OTHERS).strip()
                if source not in valid_sources:
                    source = ORDER_SOURCE.OTHERS

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
                    customer.save()
                else:
                    customer, created = Customer.objects.get_or_create(
                        phone=phone,
                        defaults={
                            "company": company or None,
                            "name": name,
                            "second_phone": second_phone or None,
                            "email": email or None,
                        }
                    )
                    if not created:
                        customer.company = company or customer.company
                        customer.name = name or customer.name
                        customer.second_phone = second_phone or customer.second_phone
                        customer.email = email or customer.email
                        customer.save()

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
                    order_request.source = source

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
                        source=source,
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
            "staff_list": CustomUser.objects.filter(
                user_type__in=[
                    USER_TYPE.STAFF, 
                    USER_TYPE.ADMIN, 
                    USER_TYPE.SUPER_ADMIN
                    ]),
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


class TelegramBotSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        configs = TelegramBotConfig.objects.all().order_by("-created_at")

        for config in configs:
            config.notify_sources_json = pyjson.dumps(config.notify_sources or [])

        context = {
            "configs": configs,
            "order_source_choices": ORDER_SOURCE.choices,
        }
        return render(request, "db_settings/telegram_bot_settings.html", context)

    def post(self, request):
        try:
            data = request.POST
            config_id = data.get("config_id")

            name = data.get("name", "").strip() or "Default Bot"
            bot_token = data.get("bot_token", "").strip()
            group_chat_id = data.get("group_chat_id", "").strip()
            is_active = data.get("is_active") == "on"
            notify_sources = data.getlist("notify_sources")

            if not bot_token or not group_chat_id:
                return JsonResponse({"status": False, "message": "Bot token and Group Chat ID are required."}, status=HTTPStatus.BAD_REQUEST)

            if config_id:
                config = get_object_or_404(TelegramBotConfig, id=config_id)
            else:
                config = TelegramBotConfig()

            if is_active:
                TelegramBotConfig.objects.exclude(id=config.id).update(is_active=False)

            config.name = name
            config.bot_token = bot_token
            config.group_chat_id = group_chat_id
            config.is_active = is_active
            config.notify_sources = notify_sources
            config.save()

            return JsonResponse({"status": True, "message": "Telegram bot settings saved successfully."}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_telegram_bot_config(request, id):
    if request.method == "DELETE":
        try:
            config = get_object_or_404(TelegramBotConfig, id=id)
            config.delete()
            return JsonResponse({"status": True, "message": "Config deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_telegram_bot_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        config = get_object_or_404(TelegramBotConfig, id=id)
        want_active = request.POST.get("is_active") == "true"
        if want_active:
            TelegramBotConfig.objects.exclude(id=config.id).update(is_active=False)
        config.is_active = want_active
        config.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Status updated", "is_active": config.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    
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



#------------------ Pixel Setup --------------


class OrderTokenPrintView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        order.status = STATUS.TOKEN_PRINT
        order.save(update_fields=["status"])

        shipment = order.shipments.select_related("courier").order_by("-created_at").first()
        due_amount = (order.total_cost or 0) - (order.advance_amount or 0)

        tokens = [{"order": order, "shipment": shipment, "due_amount": due_amount}]

        return render(request, "db_order/token.html", {"tokens": tokens})


class OrderBulkTokenPrintView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        ids_param = request.GET.get("ids", "")
        order_ids = [int(i) for i in ids_param.split(",") if i.strip().isdigit()]

        if not order_ids:
            messages.error(request, "No orders selected for token print.")
            return redirect("order_list")

        orders = Order.objects.filter(id__in=order_ids).select_related("customer").prefetch_related(
            "order_items", "shipments", "shipments__courier"
        )

        orders_by_id = {o.id: o for o in orders}
        ordered_orders = [orders_by_id[i] for i in order_ids if i in orders_by_id]

        Order.objects.filter(id__in=order_ids).update(status=STATUS.TOKEN_PRINT)

        tokens = []
        for order in ordered_orders:
            shipment = order.shipments.order_by("-created_at").first()
            due_amount = (order.total_cost or 0) - (order.advance_amount or 0)
            tokens.append({"order": order, "shipment": shipment, "due_amount": due_amount})

        return render(request, "db_order/token.html", {"tokens": tokens})


class OrderPathaoParcelSubmitView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                data = json.loads(request.body)
                logistics_partner = DeliveryOption.objects.get(id=data.get("logistics_partner"))
                order = get_object_or_404(Order, pk=pk)
                order_data = {
                    "recipient_name": order.customer.name,
                    "recipient_phone": order.customer.phone,
                    "recipient_address": order.shipping_address,
                    "amount_to_collect": float(order.total_cost),
                    "item_description": f"Order {order.order_id}",
                }
                pathao = PathaoParcelAPI(logistics_partner.id)
                pathao_response = pathao.create_order(order_data)
                shipment = order.shipments.create(
                    courier=logistics_partner,
                    tracking_number=pathao_response.get("consignment_id"),
                    status=pathao_response.get("order_status", "pending"),
                )
                return JsonResponse({"success": True, "message": "Pathao parcel created.", "tracking_number": shipment.tracking_number})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class OrderBulkActionView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        try:
            data = json.loads(request.body)

            order_ids = data.get("order_ids", [])
            action = data.get("action")

            if not order_ids:
                return JsonResponse({
                    "success": False,
                    "message": "Please select at least one order."
                }, status=400)

            orders = Order.objects.filter(id__in=order_ids)

            if not orders.exists():
                return JsonResponse({
                    "success": False,
                    "message": "No valid orders selected."
                }, status=400)


            if action == "status":

                new_status = data.get("status")

                valid_statuses = [
                    value for value, label in STATUS.choices
                ]

                if new_status not in valid_statuses:
                    return JsonResponse({
                        "success": False,
                        "message": "Invalid status selected."
                    }, status=400)

                orders.update(status=new_status)

                return JsonResponse({
                    "success": True,
                    "message": f"{orders.count()} order(s) status updated successfully."
                })


            elif action == "work_assign":

                staff_id = data.get("staff_id")

                if not staff_id:
                    return JsonResponse({
                        "success": False,
                        "message": "Please select a staff member."
                    }, status=400)

                assigned_user = get_assignable_users().filter(
                    id=staff_id
                ).first()

                if not assigned_user:
                    return JsonResponse({
                        "success": False,
                        "message": "Selected user is not available for assignment."
                    }, status=400)

                
                orders.update(
                    work_assign=assigned_user.username
                )

                return JsonResponse({
                    "success": True,
                    "message": (
                        f"{orders.count()} order(s) assigned to "
                        f"{assigned_user.get_full_name() or assigned_user.username}."
                    )
                })

            else:

                return JsonResponse({
                    "success": False,
                    "message": "Invalid bulk action."
                }, status=400)


        except json.JSONDecodeError:

            return JsonResponse({
                "success": False,
                "message": "Invalid request data."
            }, status=400)


        except Exception as e:

            return JsonResponse({
                "success": False,
                "message": str(e)
            }, status=400)


class OrderUrgentToggleView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        order.is_urgent = not order.is_urgent
        order.save(update_fields=['is_urgent'])

        status_text = "marked as urgent" if order.is_urgent else "removed from urgent list"
        message = f"Order #{order.order_id} {status_text}."
        source = request.POST.get("source", "order_list")

        if request.htmx:
            if source == "dashboard":
                dashboard_view = DashboardView()
                orders_qs = Order.objects.all().order_by("-created_at")
                is_staff = request.user.user_type == USER_TYPE.STAFF

                context = {
                    "orders": orders_qs[:10],
                    "today_order_count": dashboard_view.get_today_order_count(orders_qs),
                    "new_orders_count": dashboard_view.new_orders_count(orders_qs),
                    "status_amounts": dashboard_view.get_status_amounts(orders_qs),
                    "total_orders": orders_qs.count(),
                    "new_order_request_count": dashboard_view.new_order_request_count(),
                    "urgent_count": dashboard_view.get_urgent_count(orders_qs),
                    "short_in_stock_count": dashboard_view.get_short_in_stock_count(),
                    "out_of_stock_count": dashboard_view.get_out_of_stock_count(),
                    "total_customer_count": dashboard_view.get_total_customer_count(),
                    "status_choices": STATUS.choices,
                }
                if not is_staff:
                    context["total_order_amount"] = dashboard_view.get_total_order_amount(orders_qs)
                    context["today_sales_amount"] = dashboard_view.get_today_sales_amount(orders_qs)
                else:
                    context["total_order_amount"] = None
                    context["today_sales_amount"] = None

                response = render(request, "db_home/main_wrapper.html", context)
            else:
                order_view = OrderView()
                (orders, paginator, per_page, page_number, products) = order_view.get_order_queryset(request)
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
                response = render(request, "db_order/partial/partial_order_list.html", context)

            response["HX-Trigger"] = json.dumps({
                "showToast": {"message": message, "type": "success"}
            })
            return response

        messages.success(request, message)
        return redirect('order_list')


