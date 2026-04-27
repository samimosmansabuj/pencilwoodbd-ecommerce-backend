from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import HomeSlider, NewsFeed
from product.models import Product, Category
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS


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
                "sliders": [
                    {"image": s.image.url if s.image else None}
                    for s in sliders
                ],
                "news": [
                    {"text": n.news}
                    for n in news
                ],
                "products": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "price": p.price
                    } for p in products
                ],
                "categories": [
                    {
                        "id": c.id,
                        "name": c.name
                    } for c in categories
                ]
            }
        })