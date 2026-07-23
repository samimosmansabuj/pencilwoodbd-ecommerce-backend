from rest_framework import permissions, status, views
from rest_framework.response import Response
from authentication.models import Customer
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from product.models import Product, AddToCart
from pencilwoodbd.choices import PRODUCT_GIFT_TYPE, PAYMENT_STATUS, PAYMENT_TYPE
from django.db import transaction
from order.models import Order, OrderItem, Shipment, Address, Payment, PaymentMethod
from .utils import OrderConfirmatinoEmailSend
from site_app.models import DeliveryOption, OTPVerification
from .serializers import DeliveryOptionSerializer, ShipmentSerializer
from product.models import Product, ProductVariant
from rest_framework.permissions import IsAuthenticated, AllowAny
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from pencilwoodbd.choices import USER_TYPE
from authentication.utils import normalize_bd_phone
from site_app.delivery_charge import DeliveryChargeResolver

class DeliveryOptionListAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, *args, **kwargs):
        try:
            delivery_options = DeliveryOption.objects.filter(is_active=True)
            serializer = DeliveryOptionSerializer(delivery_options, many=True)
            return Response(
                {
                    "success": True,
                    "delivery_options": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class ShipmentSerializerAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            order_id = kwargs.get("order_id")
            shipment = Shipment.objects.filter(order__id=order_id)
            if not shipment.exists():
                return Response(
                    {
                        "success": False,
                        "message": "No shipment information found for this order."
                    }, status=status.HTTP_404_NOT_FOUND
                )
            serializer = ShipmentSerializer(shipment, many=True)
            return Response(
                {
                    "success": True,
                    "message": "Shipment information!",
                    "data": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )





class CheckoutSummaryAPIView(APIView):
    permission_classes = [AllowAny]  # CHANGED from IsAuthenticated

    def get(self, request):
        try:
            selected_district = request.query_params.get("district")
            items_data = []
            subtotal = Decimal("0")
            total_delivery_charge = Decimal("0")

            if request.user.is_authenticated and getattr(request.user, "customer_profile", None):
                customer = request.user.customer_profile
                cart_ids = request.query_params.getlist("cart_ids")
                cart_items = AddToCart.objects.filter(customer=customer)
                if cart_ids:
                    cart_items = cart_items.filter(id__in=cart_ids)

                if not cart_items.exists():
                    return Response({"status": False, "message": "Cart empty"}, status=400)

                for item in cart_items:
                    product = item.product
                    product_delivery_charge = DeliveryChargeResolver.get_charge(product, selected_district)
                    total_delivery_charge += product_delivery_charge
                    items_data.append({
                        "cart_id": item.id,
                        "product_id": product.id,
                        "product": product.name,
                        "quantity": item.quantity,
                        "price": item.price,
                        "total": item.total_price,
                        "delivery_charge": float(product_delivery_charge)
                    })
                    subtotal += item.total_price
            else:
                # GUEST: frontend sends items as JSON in query param
                import json as pyjson
                raw_items = request.query_params.get("items")
                guest_items = pyjson.loads(raw_items) if raw_items else []

                if not guest_items:
                    return Response({"status": False, "message": "Cart empty"}, status=400)

                for row in guest_items:
                    product = Product.objects.filter(id=row.get("product_id")).first()
                    if not product:
                        continue
                    variant = None
                    if row.get("variant_id"):
                        variant = ProductVariant.objects.filter(id=row["variant_id"], product=product).first()

                    quantity = int(row.get("quantity", 1))
                    price = variant.price if variant else product.price
                    discount_price = (variant.discount_price if variant else product.discount_price) or price
                    line_total = discount_price * quantity

                    product_delivery_charge = DeliveryChargeResolver.get_charge(product, selected_district)
                    total_delivery_charge += product_delivery_charge

                    items_data.append({
                        "cart_id": None,
                        "product_id": product.id,
                        "product": product.name,
                        "quantity": quantity,
                        "price": discount_price,
                        "total": line_total,
                        "delivery_charge": float(product_delivery_charge)
                    })
                    subtotal += line_total

            grand_total = subtotal + total_delivery_charge

            return Response({
                "status": True,
                "data": {
                    "items": items_data,
                    "subtotal": subtotal,
                    "delivery_charge": total_delivery_charge,
                    "grand_total": grand_total
                }
            })

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)
        
        
class PlaceOrderAPIView(APIView):
    permission_classes = [AllowAny]  # CHANGED

    def post(self, request):
        try:
            with transaction.atomic():
                phone = normalize_bd_phone(request.data.get("phone", ""))
                name = request.data.get("name")
                address_text = request.data.get("address")
                district = request.data.get("district")
                upazila = request.data.get("upazila") or "N/A"

                if not phone or not name or not address_text or not district:
                    return Response(
                        {"status": False, "message": "Name, phone, address & district required"},
                        status=400
                    )

                # Resolve/create the Customer by phone — this is the guest->customer link.
                customer, created = Customer.objects.get_or_create(
                    phone=phone,
                    defaults={"name": name}
                )
                if not created:
                    customer.name = name
                    customer.save()

                # Build the order-item list: logged-in users can pass cart_ids (DB cart),
                # guests pass "items": [{product_id, variant_id, quantity}, ...] straight from localStorage.
                if request.user.is_authenticated and getattr(request.user, "customer_profile", None):
                    # Logged in — use their real customer (in case phone differs from account, prefer account)
                    customer = request.user.customer_profile
                    cart_ids = request.data.get("cart_ids", [])
                    if not cart_ids:
                        return Response({"status": False, "message": "No cart items selected"}, status=400)

                    cart_items = AddToCart.objects.select_related("product", "variant").filter(
                        customer=customer, id__in=cart_ids
                    )
                    if not cart_items.exists():
                        return Response({"status": False, "message": "Cart empty"}, status=400)

                    line_items = [
                        {"product": ci.product, "variant": ci.variant, "quantity": ci.quantity}
                        for ci in cart_items
                    ]
                    should_delete_cart = cart_items
                else:
                    raw_items = request.data.get("items", [])
                    if not raw_items:
                        return Response({"status": False, "message": "No cart items"}, status=400)

                    line_items = []
                    for row in raw_items:
                        product = Product.objects.filter(id=row.get("product_id")).first()
                        if not product:
                            continue
                        variant = None
                        if row.get("variant_id"):
                            variant = ProductVariant.objects.filter(id=row["variant_id"], product=product).first()
                        line_items.append({
                            "product": product, "variant": variant,
                            "quantity": int(row.get("quantity", 1))
                        })

                    if not line_items:
                        return Response({"status": False, "message": "Cart empty"}, status=400)
                    should_delete_cart = None

                address = Address.objects.create(
                    customer=customer, street_01=address_text, district=district, upazila=upazila
                )

                order = Order.objects.create(
                    customer=customer,
                    shipping_address=f"{address.street_01}, {address.district}"
                )

                total = Decimal("0")
                total_delivery_charge = Decimal("0")

                for line in line_items:
                    product = line["product"]
                    variant = line["variant"]
                    quantity = line["quantity"]

                    product_delivery_charge = DeliveryChargeResolver.get_charge(product, district)
                    total_delivery_charge += product_delivery_charge

                    if variant:
                        if variant.inventory_quantity < quantity:
                            return Response({"status": False, "message": f"{product.name} out of stock"}, status=400)
                        variant.inventory_quantity -= quantity
                        variant.save()
                        product.inventory_quantity = sum(
                            v.inventory_quantity for v in product.variants.filter(is_active=True)
                        )
                        product.save(update_fields=["inventory_quantity"])
                        price = variant.price
                        discount_price = variant.discount_price or variant.price
                    else:
                        if product.inventory_quantity < quantity:
                            return Response({"status": False, "message": f"{product.name} out of stock"}, status=400)
                        product.inventory_quantity -= quantity
                        product.save(update_fields=["inventory_quantity"])
                        price = product.price
                        discount_price = product.discount_price or product.price

                    OrderItem.objects.create(
                        order=order, product=product, variant=variant, product_name=product.name,
                        quantity=quantity, price=price, discount_price=discount_price,
                    )
                    total += discount_price * quantity

                order.total_cost = total + total_delivery_charge
                order.shipping_total = total_delivery_charge
                order.save()

                if should_delete_cart is not None:
                    should_delete_cart.delete()

                return Response({
                    "status": True,
                    "message": "Order placed successfully",
                    "order_id": order.order_id
                })

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)

class OrderListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        customer = request.user.customer_profile

        orders = (
            Order.objects
            .filter(customer=customer)
            .prefetch_related(
                "order_items",
                "order_items__product",
                "order_items__product__images"
            )
            .order_by("-created_at")
        )

        data = []

        for order in orders:

            items = []

            for item in order.order_items.all():

                image = ""

                if item.product and item.product.primary_image:
                    image = request.build_absolute_uri(
                        item.product.primary_image
                    )

                items.append({
                    "name": item.product_name,
                    "qty": item.quantity,
                    "price": item.price,
                    "image": image
                })

            data.append({
                "order_id": order.order_id,
                "date": order.created_at.strftime("%d %b %Y"),
                "status": order.status,
                "payment_status": order.payment_status,
                "total": order.total_cost,

                # Reference UI er jonno
                "items": items,

                # First product image
                "thumbnail": items[0]["image"] if items else "",

                # Product count
                "item_count": order.get_total_quantity
            })

        return Response({
            "status": True,
            "data": data
        })
    



class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):

        try:

            customer = request.user.customer_profile

            order = get_object_or_404(
                Order,
                order_id=order_id,
                customer=customer
            )

            items = []
            subtotal = Decimal("0")

            for item in order.order_items.all():

                item_total = (
                    item.discount_total_price
                    if item.discount_total_price
                    else item.price * item.quantity
                )

                subtotal += item_total

                image = None

                try:

                    if (
                        item.product and
                        item.product.primary_image
                    ):
                        image = request.build_absolute_uri(
                            item.product.primary_image
                        )

                except Exception:
                    image = None

                items.append({
                    "name": (
                        item.product_name
                        or (
                            item.product.name
                            if item.product
                            else "Product"
                        )
                    ),

                    "image": image,

                    "qty": item.quantity,

                    "price": item.price,

                    "total": item_total,

                    "variant": (
                        item.variant.attributes
                        if item.variant
                        else None
                    )
                })

            data = {
                "order_id": order.order_id,

                "date": order.created_at,

                "status": order.status,

                "payment_status": order.payment_status,
                "payment_type": order.payment_type,

                "subtotal": subtotal,
                "shipping": order.shipping_total,
                "total": order.total_cost,

                "customer_name": (
                    customer.name
                    if customer
                    else ""
                ),

                "customer_phone": (
                    customer.phone
                    if customer
                    else ""
                ),

                "address": order.shipping_address,

                "items": items
            }

            return Response({
                "status": True,
                "data": data
            })

        except Exception as e:

            return Response(
                {
                    "status": False,
                    "message": str(e)
                },
                status=500
            )

class PaymentMethodListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        methods = PaymentMethod.objects.all()

        return Response({
            "status": True,
            "data": [
                {
                    "id": m.id,
                    "name": m.payment_option,
                    "account_number": m.account_number,
                    "account_name": m.account_name
                }
                for m in methods
            ]
        })


class CreatePaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            customer = request.user.customer_profile

            order_id = request.data.get("order_id")
            payment_method_id = request.data.get("payment_method_id")
            transaction_id = request.data.get("transaction_id")

            order = Order.objects.filter(
                order_id=order_id,
                customer=customer
            ).first()

            if not order:
                return Response(
                    {"status": False, "message": "Order not found"},
                    status=404
                )

            if order.payment_status == PAYMENT_STATUS.Paid:
                return Response(
                    {"status": False, "message": "Already paid"},
                    status=400
                )

            payment_method = PaymentMethod.objects.filter(
                id=payment_method_id
            ).first()

            if not payment_method:
                return Response(
                    {"status": False, "message": "Invalid payment method"},
                    status=400
                )

            payment = Payment.objects.create(
                order=order,
                payment_method=payment_method,
                provider=payment_method.payment_option,
                amount=order.total_cost,
                transaction_id=transaction_id,
                status="pending"
            )

            order.payment_type = PAYMENT_TYPE.ONLINE
            order.payment_status = PAYMENT_STATUS.Pending
            order.save()

            return Response({
                "status": True,
                "message": "Payment submitted",
                "payment_id": payment.id
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )


class VerifyPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        if request.user.user_type not in [
            USER_TYPE.ADMIN,
            USER_TYPE.SUPER_ADMIN
        ]:
            return Response(
                {"status": False, "message": "Permission denied"},
                status=403
            )

        try:
            payment_id = request.data.get("payment_id")
            status_value = request.data.get("status")

            if status_value not in ["success", "failed"]:
                return Response(
                    {"status": False, "message": "Invalid status"},
                    status=400
                )

            payment = Payment.objects.filter(
                id=payment_id
            ).select_related("order").first()

            if not payment:
                return Response(
                    {"status": False, "message": "Payment not found"},
                    status=404
                )

            payment.status = status_value
            payment.save()

            if status_value == "success":
                payment.order.payment_status = PAYMENT_STATUS.Paid
            else:
                payment.order.payment_status = PAYMENT_STATUS.Failed

            payment.order.save()

            return Response({
                "status": True,
                "message": "Payment verified"
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )





# class EcomOrderCreateAPIView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         try:
#             with transaction.atomic():

#                 data = request.data
#                 items = data.get("items", [])

#                 if not items:
#                     return Response({"status": False, "message": "No items"}, status=400)

#                 total = Decimal("0")
#                 order_items = []

#                 customer = None
#                 if request.user.is_authenticated:
#                     customer = getattr(request.user, "customer_profile", None)
#                 else:
#                     customer, _ = Customer.objects.get_or_create(
#                         phone=data.get("phone"),
#                         defaults={"name": data.get("name")}
#                     )

#                 address = Address.objects.create(
#                     customer=customer,
#                     street_01=data.get("address"),
#                     upazila=data.get("upazila"),
#                     district=data.get("district"),
#                 )

#                 order = Order.objects.create(
#                     customer=customer,
#                     shipping_address=f"{address.street_01}, {address.district}"
#                 )

#                 for item in items:
#                     product = Product.objects.filter(id=item["product_id"]).first()
#                     variant = None

#                     if item.get("variant_id"):
#                         variant = ProductVariant.objects.filter(id=item["variant_id"]).first()
#                         price = variant.price
#                         variant.inventory_quantity -= item["quantity"]
#                         variant.save()
#                     else:
#                         price = product.price
#                         product.inventory_quantity -= item["quantity"]
#                         product.save()

#                     total += price * item["quantity"]

#                     OrderItem.objects.create(
#                         order=order,
#                         product=product,
#                         variant=variant,
#                         quantity=item["quantity"],
#                         price=price
#                     )

#                 order.total_cost = total
#                 order.save()

#                 return Response({
#                     "status": True,
#                     "order_id": order.order_id
#                 })

#         except Exception as e:
#             return Response({"status": False, "message": str(e)}, status=400)
