from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import HomeSlider, NewsFeed, LandingPageProduct
from product.models import Product, Category, ProductImage, ProductVariant
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS
from django.shortcuts import get_object_or_404

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
    



class LandingPageAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            code = request.query_params.get("code")

            if not code:
                return Response(
                    {"status": False, "message": "Code is required"},
                    status=400
                )

            landing = LandingPageProduct.objects.prefetch_related(
                "product__images",
                "product__variants",
                "main_product__images",
                "main_product__variants"
            ).filter(code=code).first()

            if not landing:
                return Response(
                    {"status": False, "message": "Invalid code"},
                    status=404
                )

            main_product = landing.main_product

            def get_product_data(product):
                return {
                    "id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "discount_price": product.discount_price,
                    "image": product.primary_image,
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
                    "images": [
                        img.image.url for img in product.images.all() if img.image
                    ]
                }

            return Response({
                "status": True,
                "data": {
                    "page_name": landing.page_name,
                    "main_product": get_product_data(main_product) if main_product else None,
                    "related_products": [
                        get_product_data(p) for p in landing.product.all()
                    ]
                }
            })

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=500
            )