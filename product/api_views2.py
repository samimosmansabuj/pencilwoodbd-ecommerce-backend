from rest_framework import views, status, permissions
from rest_framework.response import Response
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from product.models import Category, Product
from product.serializers import ProductSerializer, CategorySerializer
from site_app.models import LandingPageProduct
from order.models import Order, OrderItem
from authentication.models import Customer

# ================= Tissue Box Landing Products =================
class TissueBoxLandingProductViews(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            landing_page = LandingPageProduct.objects.filter(page_name="Tissue Box").first()

            if landing_page:
                main = [landing_page.main_product] if landing_page.main_product else []
                many = list(landing_page.product.all())
                product = main + many

                return Response(
                    {
                        "status": True,
                        "data": ProductSerializer(
                            product,
                            many=True,
                            context={"request": request}
                        ).data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"status": False, "message": "Landing page product not setup."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ================= Tissue Box Landing Order =================
@method_decorator(csrf_exempt, name='dispatch')
class TissueBoxLandingOrderAPI(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            name = data.get("name")
            phone = data.get("phone")
            address = data.get("address")
            quantity = int(data.get("quantity", 1))
            UNIT_PRICE = 500  # same as your JS

            if not name or not phone or not address:
                return Response(
                    {"status": False, "message": "Name, phone and address are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get or create customer
            customer, created = Customer.objects.get_or_create(
                phone=phone,
                defaults={"name": name}
            )

            total_cost = UNIT_PRICE * quantity

            # Create order
            order = Order.objects.create(
                customer=customer,
                shipping_address=address,
                total_cost=total_cost,
                metadata={
                    "note": f"Tissue Box Landing | Name: {name} | Phone: {phone} | Qty: {quantity}"
                },
                created_at=timezone.localtime()
            )

            # Create OrderItem
            tissue_product = Product.objects.filter(name__icontains="Tissue Box").first()
            if tissue_product:
                OrderItem.objects.create(
                    order=order,
                    product=tissue_product,
                    quantity=quantity,
                    price=UNIT_PRICE,
                    discount_price=UNIT_PRICE,
                    discount_total_price=UNIT_PRICE * quantity
                )

            return Response(
                {"status": True, "message": "Order received successfully", "order_id": order.id},
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
