from rest_framework import views, status, permissions
from rest_framework.response import Response

from product.models import Category
from product.serializers import ProductSerializer, CategorySerializer
from site_app.models import LandingPageProduct
from order.models import Order


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
            quantity = data.get("quantity")

            if not name or not phone or not address:
                return Response(
                    {
                        "status": False,
                        "message": "Name, phone and address are required"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            order = Order.objects.create(
                address=address,
                note=f"Tissue Box Landing | Name: {name} | Phone: {phone} | Qty: {quantity}"
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
                {
                    "status": False,
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
