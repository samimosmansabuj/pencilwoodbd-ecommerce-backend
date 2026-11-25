from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS
from product.models import Product
from .engine import offers_for_product
from .models import ProductComboPair
from campaigns.context import offers_suppressed


class ProductOffersAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, product_id):
        product = Product.objects.filter(id=product_id, status=CATEGORY_PRODUCT_STATUS.ACTIVE).first()
        if not product:
            return Response({"status": True, "data": {"offers": [], "combos": []}})

        if offers_suppressed(request.query_params.get("campaign"), product):
            offers = []
        else:
            offers = offers_for_product(product, abs_url=request.build_absolute_uri)

        partner_ids = set()
        for a, b in ProductComboPair.objects.filter(product_a=product).values_list("product_a_id", "product_b_id"):
            partner_ids.add(b)
        for a, b in ProductComboPair.objects.filter(product_b=product).values_list("product_a_id", "product_b_id"):
            partner_ids.add(a)
        combos = []
        for p in Product.objects.filter(id__in=partner_ids, status=CATEGORY_PRODUCT_STATUS.ACTIVE):
            img = p.primary_image
            combos.append({
                "product_id": p.id, "name": p.name, "slug": p.slug,
                "price": float(p.discount_price or p.price or 0),
                "image": request.build_absolute_uri(img) if img else "",
            })
        return Response({"status": True, "data": {"offers": offers, "combos": combos}})
