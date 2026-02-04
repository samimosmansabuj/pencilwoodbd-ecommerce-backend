from rest_framework import permissions, status, views
from rest_framework.response import Response
from authentication.models import Customer
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from product.models import Product
from pencilwoodbd.choices import PRODUCT_GIFT_TYPE
from django.db import transaction
from order.models import Order, OrderItem

class OrderCreateAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        return JsonResponse(
            {
                "success": False,
                "message": "Get method not allowed!"
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    # GET AND CREATE CUSTOMER OBJECT
    def get_customer(self, data):
        customer, created = Customer.objects.get_or_create(
            phone=data.get("phone"),
            defaults={"name": data.get("name")}
        )
        return customer
    
    # MAKE ADDRESS 
    def get_make_address(self, data):
        address = f"{data.get('address')}, {data.get('district')}"
        return address
    
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
    
    # VERIFY ORDER AMOUNT 
    def verify_input_amount(self, data):
        input_delivery_charge = data["deliveryCharge"]
        data["deliveryCharge"] = "FREE" if input_delivery_charge == 0 else input_delivery_charge
        if data:
            required_fields = [
                "productTotal", "deliveryCharge", "totalAmount"
            ]
            missing_fields = [field for field in required_fields if not data.get(field)]
            data["deliveryCharge"] = input_delivery_charge
            return missing_fields
        else:
            raise Exception("Customer data must be set.")

    # HANDLING MISSING FIELD AND SEND ERROR 
    def handle_missing_field(self, data):
        customer_missing_fields = self.verify_input_customer(data.get("customer", {}))
        if customer_missing_fields:
            raise Exception(f"The following fields must be filled: {', '.join(customer_missing_fields)}")
        
        amount_missing_fields = self.verify_input_amount(data.get("amount", {}))
        if amount_missing_fields:
            raise Exception(f"The following fields must be set: {', '.join(amount_missing_fields)}")

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

    # AMOUNT CHECK BETWEEN DATA AND PRODUCT 
    def amount_check(self, data: dict) -> dict:
        if self.productTotal == data.get("productTotal" or 0):
            return data
        raise Exception("Total product amount not same.")

    # CREATE ORDER ITEM
    def create_order_item(self, order, products, amount):
        order_items = []
        for product in products:
            prod = Product.objects.get(pk=product.get("id"))
            order_item = OrderItem.objects.create(
                order=order,
                product=prod,
                quantity=product.get("quantity"),
                price=prod.price,
                discount_price=product.get("price"),
            )
            order_items.append(order_item)
        return order_items

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                data = request.data                
                self.handle_missing_field(data)

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

                return Response(
                    {
                        "success": True,
                        "message": "Order Created"
                    }, status=status.HTTP_201_CREATED
                )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
