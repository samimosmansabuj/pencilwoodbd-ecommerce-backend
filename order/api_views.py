from rest_framework import permissions, status, views
from rest_framework.response import Response
from authentication.models import Customer
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from product.models import Product
from pencilwoodbd.choices import PRODUCT_GIFT_TYPE
from django.db import transaction
from order.models import Order, OrderItem, Shipment
from .utils import OrderConfirmatinoEmailSend
from site_app.models import DeliveryOption, OTPVerification
from .serializers import DeliveryOptionSerializer, ShipmentSerializer

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
                    phone = customer_data.get("phone")

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

                # ✅ OTP delete after successful order
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
