from rest_framework import views, status, permissions, viewsets
from rest_framework.response import Response
from .serializers import ProductSerializer, CategorySerializer
from site_app.models import LandingPageProduct, OTPVerification
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from authentication.models import Customer
from order.models import Order, OrderItem
from product.models import Product, Category, ProductVariant, ProductImage, AddToCart
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from pencilwoodbd.choices import STATUS, PAYMENT_TYPE, PAYMENT_STATUS, CATEGORY_PRODUCT_STATUS, DELIVERY_TYPE, PRODUCT_GIFT_TYPE
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.db.models import Prefetch
from django.db.models import Prefetch, Case, When

import random
import requests
from rest_framework.views import APIView
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from .models import Wishlist

class CategoryAPIViews(views.APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, *args, **kwargs):
        try:
            category_id = request.query_params.get('category')
            if category_id:
                try:
                    category = Category.objects.get(id=category_id)
                    sub_category = category.children.all()
                    return Response(
                        {
                            "status": True,
                            "data": CategorySerializer(sub_category, many=True).data
                        }, status=status.HTTP_200_OK
                    )
                except Category.DoesNotExist:
                    return Response(
                        {
                            "status": False,
                            "message": "Category not found"
                        }, status=status.HTTP_404_NOT_FOUND
                    )
            categories = Category.objects.filter(parent__isnull=True)
            return Response(
                {
                    "status": True,
                    "data": CategorySerializer(categories, many=True, context={"request": request}).data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )






# otp/views.py
import os
class SendOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get_phone_number(self, request):
        phone = request.data.get("phone", "").strip()
        phone = phone.strip()
        if not phone.startswith("88"):
            phone = "88" + phone
        return phone
    
    def send_message(self, phone, otp):
        url = "https://console.smsq.global/api/v3/SendSMS"
        payload = {
            "senderId": os.getenv("sender_id"),
            "is_Unicode": True,
            "is_Flash": False,
            "message": f"Number Verification OTP {otp} for PencilwoodBD. Do not share this OTP with anyone.",
            "mobileNumbers": phone,
            "apiKey": os.getenv("api_key"),
            "clientId": os.getenv("client_id")
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def post(self, request):
        phone = self.get_phone_number(request)
        otp = str(random.randint(100000, 999999))
        try:
            with transaction.atomic():
                response = self.send_message(phone, otp)
                if (
                    response.get("ErrorCode") == 0 and
                    response.get("Data") and
                    response["Data"][0].get("MessageErrorCode") == 0 and
                    response["Data"][0].get("MessageErrorDescription") == "Success"
                ):
                    OTPVerification.objects.create(phone=phone, otp=otp)
                    return Response({"success": True, "message": "OTP Sent"})
                else:
                    return Response({"success": False, "message": "OTP Sending Failed", "response": response})
        except Exception as e:
            return Response({"success": False, "message": str(e)})
        
class VerifyOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get_phone_number(self, request):
        phone = request.data.get("phone", "").strip()
        phone = phone.strip()
        if not phone.startswith("88"):
            phone = "88" + phone
        return phone
    
    def post(self, request):
        phone = self.get_phone_number(request)
        otp = request.data.get("otp")
        try:
            otp_obj = OTPVerification.objects.filter(phone=phone).last()
            if not otp_obj:
                return Response({"verified": False, "message": "No OTP found"})
            if otp_obj.is_expired():
                return Response({"verified": False, "message": "OTP expired"})
            if otp_obj.otp != otp:
                return Response({"verified": False, "message": "Invalid OTP"})
            otp_obj.is_verified = True
            otp_obj.save()
            return Response({"verified": True})
        except Exception as e:
            return Response({"verified": False, "message": str(e)})



class ProductPagination(PageNumberPagination):
    page_size = 10


class CategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        parent = request.query_params.get("parent")

        qs = Category.objects.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE)

        if parent:
            qs = qs.filter(parent_id=parent)
        else:
            qs = qs.filter(parent__isnull=True)

        return Response({
            "status": True,
            "data": [
                {
                    "id": c.id,
                    "name": c.name,
                    "slug": c.slug,
                    "icon": c.icon,
                    "banner": c.banner_image.url if c.banner_image else None
                } for c in qs
            ]
        })

class ProductListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Product.objects.filter(
            status=CATEGORY_PRODUCT_STATUS.ACTIVE
        ).select_related("category").prefetch_related("images", "variants").order_by("-id")

        # FILTERS
        category = request.query_params.get("category")
        search = request.query_params.get("search")
        min_price = request.query_params.get("min_price")
        max_price = request.query_params.get("max_price")

        if category:
            qs = qs.filter(category_id=category)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(short_description__icontains=search) |
                Q(category__name__icontains=search) |
                Q(slug__icontains=search)
            )

        if min_price:
            qs = qs.filter(price__gte=min_price)

        if max_price:
            qs = qs.filter(price__lte=max_price)

        # SORTING
        sort = request.query_params.get("sort")

        if sort == "price_low":
            qs = qs.order_by("price")
        elif sort == "price_high":
            qs = qs.order_by("-price")
        elif sort == "newest":
            qs = qs.order_by("-created_at")
        else:
            qs = qs.order_by("-id")

        # PAGINATION
        paginator = ProductPagination()
        page = paginator.paginate_queryset(qs, request)

        return paginator.get_paginated_response({
            "status": True,
            "data": [
                {
                "id": p.id,
                "slug": p.slug,
                "name": p.name,
                "price": p.price,
                "discount_price": p.discount_price,
                "image": p.primary_image,
                "has_variants": p.has_variants,
                "category": {
                    "id": p.category.id if p.category else None,
                    "name": p.category.name if p.category else ""
                }
            }
                for p in page
            ]
        })

class ProductDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            p = Product.objects.prefetch_related(
                "images",
                "variants",
                "variants__images"
            ).filter(slug=slug).first()

            if not p:
                return Response({"status": False}, status=404)

            # Stock Calculation
            if p.has_variants:
                stock = sum(
                    v.inventory_quantity
                    for v in p.variants.filter(is_active=True)
                )
            else:
                stock = p.inventory_quantity

            return Response({
                "status": True,
                "data": {
                    "id": p.id,
                    "slug": p.slug,
                    "name": p.name,
                    "price": p.price,
                    "discount_price": p.discount_price,
                    "stock": stock,
                    "description": p.short_description,
                    "images": [
                        i.image.url for i in p.images.all() if i.image
                    ],
                    "variants": [
                        {
                            "id": v.id,
                            "attributes": v.attributes,
                            "price": v.price,
                            "discount_price": v.discount_price,
                            "stock": v.inventory_quantity,
                            "image": (
                                v.images.first().image.url
                                if v.images.exists() else None
                            ),
                        }
                        for v in p.variants.all()
                    ]
                }
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )
    
class AddToCartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            with transaction.atomic():
                customer = request.user.customer_profile

                product_id = request.data.get("product_id")
                variant_id = request.data.get("variant_id")
                quantity = int(request.data.get("quantity", 1))

                product = Product.objects.get(id=product_id)
                variant = None

                if product.has_variants:
                    if not variant_id:
                        return Response({"status": False, "message": "Variant required"}, status=400)

                    variant = ProductVariant.objects.get(id=variant_id, product=product)

                    if variant.inventory_quantity < quantity:
                        return Response({"status": False, "message": "Selected variant out of stock"}, status=400)
                else:
                    if product.inventory_quantity < quantity:
                        return Response({"status": False, "message": "Product out of stock"}, status=400)

                cart_item, created = AddToCart.objects.get_or_create(
                    customer=customer,
                    product=product,
                    variant=variant,
                    defaults={"quantity": quantity}
                )

                if not created:
                    cart_item.quantity += quantity
                    cart_item.save()

                return Response({
                    "status": True,
                    "message": "Added to cart"
                })

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=400)

class CartListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            customer = request.user.customer_profile

            cart_items = AddToCart.objects.filter(customer=customer)

            data = []
            total = Decimal("0")

            for item in cart_items:
                data.append({
                    "id": item.id,
                    "product": item.product.name,
                    "image": item.product.primary_image,
                    "variant": item.variant.attributes if item.variant else None,
                    "quantity": item.quantity,
                    "price": item.price,
                    "total": item.total_price
                })
                total += item.total_price

            return Response({
                "status": True,
                "data": data,
                "cart_total": total
            })

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=400)

class UpdateCartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, cart_id):
        try:
            customer = request.user.customer_profile
            quantity = int(request.data.get("quantity"))

            cart_item = AddToCart.objects.get(id=cart_id, customer=customer)
            cart_item.quantity = quantity
            cart_item.save()

            return Response({"status": True, "message": "Cart updated"})

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=400)
        
class RemoveCartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, cart_id):
        try:
            customer = request.user.customer_profile

            cart_item = AddToCart.objects.get(id=cart_id, customer=customer)
            cart_item.delete()

            return Response({"status": True, "message": "Removed from cart"})

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=400)
        


class AddToWishlistAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            customer = request.user.customer_profile
            product_id = request.data.get("product_id")

            product = get_object_or_404(Product, id=product_id)

            obj, created = Wishlist.objects.get_or_create(
                customer=customer,
                product=product
            )

            if not created:
                return Response({
                    "status": False,
                    "message": "Already in wishlist"
                }, status=400)

            return Response({
                "status": True,
                "message": "Added to wishlist"
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )

class WishlistAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            customer = request.user.customer_profile

            items = Wishlist.objects.filter(customer=customer).select_related("product")

            data = []

            for item in items:
                p = item.product

                data.append({
                    "id": item.id,
                    "product_id": p.id,
                    "slug": p.slug,
                    "name": p.name,
                    "price": p.price,
                    "discount_price": p.discount_price,
                    "image": p.primary_image,
                })

            return Response({
                "status": True,
                "data": data
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )

class RemoveWishlistAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, wishlist_id):
        try:
            customer = request.user.customer_profile

            item = get_object_or_404(
                Wishlist,
                id=wishlist_id,
                customer=customer
            )

            item.delete()

            return Response({
                "status": True,
                "message": "Removed from wishlist"
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )
        




# class UnifiedLandingProductAPIView(views.APIView):
#     permission_classes = [permissions.AllowAny]

#     def get(self, request, *args, **kwargs):
#         try:
#             code = request.query_params.get("code")

#             landing_page = (
#                 LandingPageProduct.objects.filter(code=code).first()
#                 if code else LandingPageProduct.objects.first()
#             )

#             if not landing_page:
#                 return Response(
#                     {"status": False, "message": "Landing page product not setup."},
#                     status=status.HTTP_404_NOT_FOUND
#                 )

#             main_product = landing_page.main_product
#             sub_products = landing_page.product.all()

#             if main_product:
#                 sub_products = sub_products.exclude(id=main_product.id)

#             products = []

#             if main_product:
#                 products.append(main_product)

#             products.extend(list(sub_products))

#             return Response(
#                 {
#                     "status": True,
#                     "data": ProductSerializer(
#                         products,
#                         many=True,
#                         context={"request": request}
#                     ).data
#                 },
#                 status=status.HTTP_200_OK
#             )

#         except Exception as e:
#             return Response(
#                 {"status": False, "message": str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        


# @method_decorator(csrf_exempt, name='dispatch')
# class UnifiedLandingOrderAPIView(views.APIView):
#     permission_classes = [permissions.AllowAny]

#     # ================= CUSTOMER =================
#     def get_customer(self, data):
#         phone = data.get("phone")
#         name = data.get("name")

#         if not phone or not name:
#             raise ValueError("Name and phone required")

#         customer, _ = Customer.objects.get_or_create(
#             phone=phone,
#             defaults={"name": name}
#         )
#         return customer

#     # ================= ADDRESS =================
#     def get_address(self, data):
#         address = data.get("address")
#         district = data.get("district")

#         if not address or not district:
#             raise ValueError("Address and district required")

#         return f"{address}, {district}"

#     # ================= FREE PRODUCT CHECK =================
#     def check_free_product(self, reference_product_id, product):
#         if not reference_product_id:
#             return False

#         reference = Product.objects.filter(id=reference_product_id).first()
#         if not reference:
#             return False

#         return reference.gift_product.filter(
#             gift_type=PRODUCT_GIFT_TYPE.FREE,
#             gift_product_id=product.id
#         ).exists()

#     # ================= CART VALIDATION =================
#     def validate_cart_products(self, product_data):
#         items = []
#         total = Decimal("0")

#         for prod in product_data:

#             product = Product.objects.select_for_update().filter(
#                 id=prod.get("id")
#             ).first()

#             if not product:
#                 raise ValueError("Product not found")

#             qty = int(prod.get("quantity") or 1)

#             actual_price = Decimal(str(product.discount_price or product.price))

#             try:
#                 sent_price = (
#                     Decimal(str(prod.get("price")))
#                     if prod.get("price") not in [None, ""]
#                     else actual_price
#                 )
#             except:
#                 raise ValueError("Invalid price format")

#             # FREE CHECK
#             if prod.get("product_type") == "FREE":
#                 if not self.check_free_product(
#                     prod.get("reference_product"),
#                     product
#                 ):
#                     raise ValueError("Invalid free product")

#             # PRICE LOCK
#             if sent_price != actual_price:
#                 raise ValueError("Price mismatch")

#             # STOCK CHECK
#             if product.inventory_quantity < qty:
#                 raise ValueError("Out of stock")

#             items.append((product, qty))
#             total += actual_price * qty

#         return items, total

#     # ================= LANDING VALIDATION =================
#     def validate_landing_order(self, variant, product, data):
#         try:
#             unit_price = Decimal(str(data.get("unit_price") or 0))
#             subtotal = Decimal(str(data.get("subtotal") or 0))
#             delivery = Decimal(str(data.get("delivery") or 0))
#             total = Decimal(str(data.get("total") or 0))
#         except:
#             raise ValueError("Invalid price format")

#         qty = int(data.get("quantity") or 1)

#         expected_price = Decimal(str(
#             variant.discount_price if variant else (product.discount_price or product.price)
#         ))

#         if expected_price <= 0:
#             raise ValueError("Invalid product price")

#         if unit_price != expected_price:
#             raise ValueError("Unit price mismatch")

#         if subtotal != expected_price * qty:
#             raise ValueError("Subtotal mismatch")

#         if total != subtotal + delivery:
#             raise ValueError("Total mismatch")

#         return total, qty, delivery, expected_price

#     # ================= MAIN =================
#     def post(self, request, *args, **kwargs):
#         try:
#             with transaction.atomic():
#                 data = request.data

#                 # ================= CART FLOW =================
#                 if data.get("products"):
#                     customer = self.get_customer(data.get("customer", {}))
#                     address = self.get_address(data.get("customer", {}))

#                     items, product_total = self.validate_cart_products(
#                         data.get("products")
#                     )

#                     amount = data.get("amount", {})

#                     product_total_sent = Decimal(str(amount.get("productTotal") or 0))
#                     delivery = Decimal(str(amount.get("deliveryCharge") or 0))
#                     total_sent = Decimal(str(amount.get("totalAmount") or 0))

#                     if product_total_sent != product_total:
#                         raise ValueError("Product total mismatch")

#                     if total_sent != product_total + delivery:
#                         raise ValueError("Final total mismatch")

#                     order = Order.objects.create(
#                         customer=customer,
#                         shipping_address=address,
#                         shipping_total=delivery,
#                         total_cost=total_sent,
#                         status=STATUS.NEW
#                     )

#                     for product, qty in items:
#                         price = Decimal(str(product.discount_price or product.price))

#                         OrderItem.objects.create(
#                             order=order,
#                             product=product,
#                             quantity=qty,
#                             price=price,
#                             discount_price=price,
#                             discount_total_price=price * qty
#                         )

#                         # SAFE INVENTORY UPDATE
#                         product.inventory_quantity = max(
#                             0,
#                             product.inventory_quantity - qty
#                         )
#                         product.save(update_fields=["inventory_quantity"])

#                     return Response(
#                         {"status": True, "message": "Order Created"},
#                         status=status.HTTP_201_CREATED
#                     )

#                 # ================= LANDING FLOW =================
#                 variant_id = data.get("variant_id")
#                 product_id = data.get("product_id")

#                 if not variant_id and not product_id:
#                     raise ValueError("Product or variant required")

#                 if variant_id:
#                     variant = ProductVariant.objects.select_for_update().select_related("product").filter(
#                         id=variant_id
#                     ).first()

#                     if not variant:
#                         raise ValueError("Variant not found")

#                     product = variant.product

#                 else:
#                     product = Product.objects.select_for_update().filter(
#                         id=product_id
#                     ).first()

#                     if not product:
#                         raise ValueError("Product not found")

#                     if product.has_variants:
#                         variant = product.variants.filter(is_active=True).first()
#                         if not variant:
#                             raise ValueError("No active variant found")
#                     else:
#                         variant = None

#                 total, qty, delivery, price = self.validate_landing_order(
#                     variant, product, data
#                 )

#                 customer = self.get_customer(data)
#                 address = self.get_address(data)

#                 order = Order.objects.create(
#                     customer=customer,
#                     shipping_address=address,
#                     shipping_total=delivery,
#                     total_cost=total,
#                     status=STATUS.NEW
#                 )

#                 OrderItem.objects.create(
#                     order=order,
#                     product=product,
#                     variant=variant,
#                     quantity=qty,
#                     price=price,
#                     discount_price=price,
#                     discount_total_price=price * qty
#                 )

#                 # SAFE INVENTORY UPDATE
#                 if variant:
#                     variant.inventory_quantity = max(0, variant.inventory_quantity - qty)
#                     variant.save()

#                     product.inventory_quantity = sum(
#                         v.inventory_quantity for v in product.variants.filter(is_active=True)
#                     )
#                     product.save(update_fields=["inventory_quantity"])
#                 else:
#                     product.inventory_quantity = max(0, product.inventory_quantity - qty)
#                     product.save(update_fields=["inventory_quantity"])

#                 return Response(
#                     {"status": True, "message": "Order received successfully"},
#                     status=status.HTTP_201_CREATED
#                 )

#         except Exception as e:
#             return Response(
#                 {"status": False, "message": str(e)},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        



