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


class OrderCreateAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        return JsonResponse(
            {
                "success": False,
                "message": "Get method not allowed!"
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    # AMOUNT CHECK BETWEEN DATA AND PRODUCT 
    def amount_check(self, data: dict) -> dict:
        if self.productTotal == data.get("productTotal" or 0):
            return data
        raise Exception("Total product amount not same.")

    # CREATE ORDER ITEM
    def create_order_item(self, order: object, products, amount):
        print("products: ", products)
        order_items = []
        for product in products:
            prod = Product.objects.get(pk=product.get("id"))
            order_item = OrderItem.objects.create(
                order=order,
                product=prod,
                quantity=product.get("quantity" or 1),
                price=prod.price,
                discount_price=product.get("price" or 0),
                discount_total_price=float(product.get("quantity" or 1)) * float(product.get("price" or 0))
            )
            order_items.append(order_item)
        return order_items

    # CHECK FREE PRODUCT FOR MAIN PRODUCT 
    def check_free_product(self, reference_product: int, product: object):
        reference = Product.objects.get(pk=reference_product)
        if not reference:
            return False
        for gift_product_object in reference.gift_product.filter(gift_type=PRODUCT_GIFT_TYPE.FREE):
            if product == gift_product_object.gift_product:
                return True
        return False

    # GET AND VERIFY PRODUCT AND PRICE DETAILS 
    def get_product_and_verify(self, product_data: dict) -> object:
        products = []
        self.productTotal = 0
        for prod in product_data:
            product = get_object_or_404(Product, pk=prod.get("id", None))
            if not product:
                raise Exception("No Product Found.")
            
            product_type = prod.get("product_type")
            reference_product = prod.get("reference_product" or None)
            if product_type == "FREE" and reference_product:
                if self.check_free_product(reference_product, product) is False:
                    raise Exception("Free Product not available.")
                products.append(product)
            elif product.discount_price != float(prod.get("price")):
                raise Exception("Product price and given price are not same.")
            elif product.inventory_quantity < prod.get("quantity"):
                raise Exception("Product not available in our Inventory.")
            else:
                self.productTotal += product.discount_price * prod.get("quantity")
                products.append(product)
        return products

    # MAKE ADDRESS 
    def get_make_address(self, data):
        address = f"{data.get('address')}, {data.get('district')}"
        return address

    # GET AND CREATE CUSTOMER OBJECT
    def get_customer(self, data):
        customer, created = Customer.objects.get_or_create(
            phone=data.get("phone"),
            defaults={"name": data.get("name")}
        )
        return customer

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                data = request.data
                self.handle_missing_field(data)

                otp_verified = None
                otp_required = bool(data.get("otp_required", False))
                
                if otp_required:
                    customer_data = data.get("customer", {})
                    
                    phone = customer_data.get("phone", "").strip()
                    if not phone.startswith("88"):
                        phone = "88" + phone

                    otp_verified = OTPVerification.objects.filter(
                        phone=phone,
                        is_verified=True
                    ).last()

                    if not otp_verified:
                        raise Exception("OTP not verified")

                    if otp_verified.is_expired():
                        raise Exception("OTP expired")
                customer = self.get_customer(data.get("customer", {}))
                address = self.get_make_address(data.get("customer", {}))
                products = self.get_product_and_verify(data.get("products", {}))
                amount = self.amount_check(data.get("amount", {}))

                order = Order.objects.create(
                    customer=customer,
                    shipping_address=address,
                    shipping_total=amount.get("deliveryCharge" or 0),
                    total_cost=amount.get("totalAmount" or 0)
                )
                order_item = self.create_order_item(order, data.get("products", {}), amount)

                if otp_required and otp_verified:
                    otp_verified.delete()

                if data.get("customer", {}).get("email", None):
                    send_mail = OrderConfirmatinoEmailSend(order, data.get("customer", {}).get("email", None))
                    send_mail.order_confirmation_mail_send()

                return Response(
                    {
                        "success": True,
                        "message": "Order Created"
                    }, status=status.HTTP_201_CREATED
                )
        except Exception as e:
            print("error: ", str(e))
            return Response(
                {
                    "success": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
    
    # VERIFY ORDER AMOUNT 
    def verify_input_amount(self, data):
        if data:
            input_delivery_charge = data["deliveryCharge"]
            data["deliveryCharge"] = "FREE" if input_delivery_charge == 0 else input_delivery_charge
            required_fields = [
                "productTotal", "deliveryCharge", "totalAmount"
            ]
            missing_fields = [field for field in required_fields if not data.get(field)]
            data["deliveryCharge"] = input_delivery_charge
            return missing_fields
        else:
            raise Exception("Customer amount must be set.")

    # VERIFY ORDER CUSTOMER INFORMATION
    def verify_input_customer(self, data):
        if data:
            required_fields = [
                "name", "phone", "address", "district",
            ]
            missing_fields = [field for field in required_fields if not data.get(field)]
            return missing_fields
        else:
            raise Exception("Customer data must be set.")

    # HANDLING MISSING FIELD AND SEND ERROR 
    def handle_missing_field(self, data):
        customer_missing_fields = self.verify_input_customer(data.get("customer", {}))
        print("customer_missing_fields: ", customer_missing_fields)
        if customer_missing_fields:
            raise Exception(f"The following fields must be filled: {', '.join(customer_missing_fields)}")
        
        amount_missing_fields = self.verify_input_amount(data.get("amount", {}))
        if amount_missing_fields:
            raise Exception(f"The following fields must be set: {', '.join(amount_missing_fields)}")

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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            customer = request.user.customer_profile

            cart_items = AddToCart.objects.filter(customer=customer)

            if not cart_items.exists():
                return Response(
                    {"status": False, "message": "Cart is empty"},
                    status=400
                )

            items_data = []
            total = Decimal("0")

            for item in cart_items:
                items_data.append({
                    "product": item.product.name,
                    "quantity": item.quantity,
                    "price": item.price,
                    "total": item.total_price
                })
                total += item.total_price

            # simple delivery logic (you can upgrade later)
            delivery_charge = Decimal("60")

            return Response({
                "status": True,
                "data": {
                    "items": items_data,
                    "subtotal": total,
                    "delivery_charge": delivery_charge,
                    "grand_total": total + delivery_charge
                }
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )
        

class PlaceOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            with transaction.atomic():

                customer = request.user.customer_profile
                cart_items = AddToCart.objects.filter(customer=customer)

                if not cart_items.exists():
                    return Response(
                        {"status": False, "message": "Cart is empty"},
                        status=400
                    )

                address_text = request.data.get("address")
                district = request.data.get("district")
                upazila = request.data.get("upazila")

                if not address_text:
                    return Response(
                        {"status": False, "message": "Address required"},
                        status=400
                    )

                address = Address.objects.create(
                    customer=customer,
                    street_01=address_text,
                    district=district,
                    upazila=upazila
                )

                order = Order.objects.create(
                    customer=customer,
                    shipping_address=f"{address.street_01}, {address.district}"
                )

                total = Decimal("0")

                for item in cart_items:

                    product = item.product
                    variant = item.variant

                    # stock validation
                    if variant:
                        if variant.inventory_quantity < item.quantity:
                            return Response(
                                {"status": False, "message": f"{product.name} out of stock"},
                                status=400
                            )
                        variant.inventory_quantity -= item.quantity
                        variant.save()
                        price = variant.discount_price or variant.price

                    else:
                        if product.inventory_quantity < item.quantity:
                            return Response(
                                {"status": False, "message": f"{product.name} out of stock"},
                                status=400
                            )
                        product.inventory_quantity -= item.quantity
                        product.save()
                        price = product.discount_price or product.price

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        variant=variant,
                        quantity=item.quantity,
                        price=price
                    )

                    total += price * item.quantity

                # delivery
                delivery_charge = Decimal("60")

                order.total_cost = total + delivery_charge
                order.shipping_total = delivery_charge
                order.save()

                # CLEAR CART
                cart_items.delete()

                return Response({
                    "status": True,
                    "message": "Order placed successfully",
                    "order_id": order.order_id
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


class OrderListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = getattr(request.user, "customer_profile", None)

        orders = Order.objects.filter(customer=customer)

        return Response({
            "status": True,
            "data": [
                {
                    "order_id": o.order_id,
                    "total": o.total_cost,
                    "status": o.status
                } for o in orders
            ]
        })


class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            customer = getattr(request.user, "customer_profile", None)

            if not customer:
                return Response(
                    {"status": False, "message": "Customer not found"},
                    status=404
                )

            order = get_object_or_404(
                Order,
                order_id=order_id,
                customer=customer
            )

            data = {
                "order_id": order.order_id,
                "status": order.status,
                "payment_status": order.payment_status,
                "total": order.total_cost,
                "delivery": order.shipping_total,
                "address": order.shipping_address,
                "date": order.created_at,
                "items": [
                    {
                        "product": i.product.name,
                        "variant": i.variant.attributes if i.variant else None,
                        "quantity": i.quantity,
                        "price": i.price,
                        "total": i.discount_total_price
                    }
                    for i in order.order_items.all()
                ]
            }

            return Response({"status": True, "data": data})

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
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

            order = Order.objects.filter(order_id=order_id, customer=customer).first()

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

            payment_method = PaymentMethod.objects.filter(id=payment_method_id).first()

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

            # update order
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
        try:
            if request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]:
                return Response(
                    {"status": False, "message": "Permission denied"},
                    status=403
                )

            payment_id = request.data.get("payment_id")
            status_value = request.data.get("status")

            if status_value not in ["success", "failed"]:
                return Response(
                    {"status": False, "message": "Invalid status"},
                    status=400
                )

            payment = Payment.objects.filter(id=payment_id).select_related("order").first()

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