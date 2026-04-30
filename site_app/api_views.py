from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from django.db import transaction
from django.db.models import F
from decimal import Decimal

from .models import HomeSlider, NewsFeed, LandingPageProduct
from product.models import Product, Category
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, STATUS
from order.models import Order, OrderItem
from authentication.models import Customer


# =========================
# HOME PAGE
# =========================
class HomePageAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sliders = HomeSlider.objects.filter(is_active=True)
        news = NewsFeed.objects.filter(is_active=True)

        products = Product.objects.filter(
            status=CATEGORY_PRODUCT_STATUS.ACTIVE
        )[:10]

        categories = Category.objects.filter(
            status=CATEGORY_PRODUCT_STATUS.ACTIVE,
            parent__isnull=True
        )

        return Response({
            "status": True,
            "data": {
                "sliders": [{"image": s.image.url if s.image else None} for s in sliders],
                "news": [{"text": n.news} for n in news],
                "products": [
                    {"id": p.id, "name": p.name, "price": p.price}
                    for p in products
                ],
                "categories": [
                    {"id": c.id, "name": c.name}
                    for c in categories
                ]
            }
        })


# =========================
# LANDING PAGE (READ ONLY)
# =========================
class LandingPageAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get("code")

        if not code:
            return Response({"status": False, "message": "Code is required"}, status=400)

        landing = LandingPageProduct.objects.select_related(
            "main_product"
        ).prefetch_related(
            "main_product__variants",
            "product"
        ).filter(code=code, is_active=True).first()

        if not landing or not landing.main_product:
            return Response({"status": False, "message": "Invalid landing page"}, status=404)

        product = landing.main_product

        return Response({
            "status": True,
            "data": {
                "code": landing.code,
                "page_name": landing.page_name,
                "title": landing.title,
                "description": landing.description,

                "product": {
                    "id": product.id,
                    "name": product.name,
                    "price": landing.price or product.price,
                    "discount_price": landing.discount_price or product.discount_price,
                    "image": landing.image.url if landing.image else product.primary_image,

                    "variants": [
                        {
                            "id": v.id,
                            "attributes": v.attributes,
                            "price": v.price,
                            "discount_price": v.discount_price,
                            "stock": v.inventory_quantity
                        }
                        for v in product.variants.filter(is_active=True)
                    ],
                },

                "upsell_products": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "price": p.price,
                        "image": p.primary_image
                    }
                    for p in landing.product.all()
                ],

                "delivery_charge": landing.delivery_charge,
            }
        })


# =========================
# LANDING ORDER (SAFE FINAL VERSION)
# =========================
class LandingOrderAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            with transaction.atomic():

                data = request.data

                code = data.get("code")
                name = data.get("name")
                phone = data.get("phone")
                address = data.get("address")
                district = data.get("district")
                quantity = int(data.get("quantity", 1))

                # ---------------- VALIDATION ----------------
                if not all([code, name, phone, address, district]):
                    return Response({"status": False, "message": "Missing fields"}, status=400)

                if quantity < 1 or quantity > 5:
                    return Response({"status": False, "message": "Invalid quantity"}, status=400)

                # ---------------- LOCK LANDING ----------------
                landing = LandingPageProduct.objects.select_related(
                    "main_product"
                ).select_for_update().filter(
                    code=code,
                    is_active=True
                ).first()

                if not landing or not landing.main_product:
                    return Response({"status": False, "message": "Invalid landing page"}, status=404)

                product = Product.objects.select_for_update().get(id=landing.main_product.id)

                # ---------------- PRICE ----------------
                price = landing.discount_price or landing.price or product.discount_price or product.price
                unit_price = Decimal(str(price))
                subtotal = unit_price * quantity

                # ---------------- SAFE STOCK CHECK + UPDATE ----------------
                updated = Product.objects.filter(
                    id=product.id,
                    inventory_quantity__gte=quantity
                ).update(
                    inventory_quantity=F("inventory_quantity") - quantity
                )

                if not updated:
                    return Response({"status": False, "message": "Out of stock"}, status=400)

                # ---------------- CUSTOMER ----------------
                customer, _ = Customer.objects.get_or_create(
                    phone=phone,
                    defaults={"name": name}
                )

                delivery = Decimal(str(landing.delivery_charge or 0))
                total = subtotal + delivery

                # ---------------- ORDER ----------------
                order = Order.objects.create(
                    customer=customer,
                    shipping_address=f"{address}, {district}",
                    shipping_total=delivery,
                    total_cost=total,
                    status=STATUS.NEW
                )

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    variant=None,
                    quantity=quantity,
                    price=unit_price,
                    discount_price=unit_price,
                    discount_total_price=subtotal
                )

                return Response({
                    "status": True,
                    "message": "Order placed successfully",
                    "order_id": order.order_id
                })

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)