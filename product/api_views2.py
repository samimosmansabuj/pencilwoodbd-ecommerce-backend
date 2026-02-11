from rest_framework import views, status, permissions
from rest_framework.response import Response
from django.utils import timezone

from product.models import Category
from product.serializers import ProductSerializer, CategorySerializer
from site_app.models import LandingPageProduct
from order.models import Order
from authentication.models import *

class CategoryAPIViews2(views.APIView):
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
                        },
                        status=status.HTTP_200_OK
                    )
                except Category.DoesNotExist:
                    return Response(
                        {
                            "status": False,
                            "message": "Category not found"
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )

            categories = Category.objects.filter(parent__isnull=True)
            return Response(
                {
                    "status": True,
                    "data": CategorySerializer(
                        categories,
                        many=True,
                        context={"request": request}
                    ).data
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
                    {
                        "status": False,
                        "message": "Landing page product not setup."
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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

            # Check if customer already exists, else create
            customer, created = Customer.objects.get_or_create(
                phone=phone,
                defaults={"name": name}
            )

            total_cost = UNIT_PRICE * quantity

            order = Order.objects.create(
                customer=customer,
                shipping_address=address,
                total_cost=total_cost,
                metadata={
                    "note": f"Tissue Box Landing | Name: {name} | Phone: {phone} | Qty: {quantity}"
                },
                created_at=timezone.localtime()
            )

            return Response(
                {
                    "status": True,
                    "message": "Order received successfully",
                    "order_id": order.id
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

