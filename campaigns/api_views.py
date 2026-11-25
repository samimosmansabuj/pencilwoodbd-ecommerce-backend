from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from pencilwoodbd.choices import CAMPAIGN_STATUS, CATEGORY_PRODUCT_STATUS
from product.api_views import _listing_price_fields
from product.models import ProductGifting

from .context import gift_fields
from .models import Campaign, CampaignProduct
from .pricing import build_campaign_pricing, effective_switches, get_campaign_status, get_sold_units_map
from .serializers import campaign_detail_dict, campaign_public_dict, primary_image_url


class CampaignListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        now = timezone.now()
        qs = Campaign.objects.filter(is_active=True, end_at__gte=now)
        if request.query_params.get("home") in ("1", "true", "True"):
            qs = qs.filter(show_on_home=True)

        live, upcoming = [], []
        for campaign in qs:
            status = get_campaign_status(campaign, now)
            if status == CAMPAIGN_STATUS.LIVE:
                live.append(campaign)
            elif status == CAMPAIGN_STATUS.UPCOMING:
                upcoming.append(campaign)

        live.sort(key=lambda c: (c.end_at, c.sort_order, c.id))
        upcoming.sort(key=lambda c: (c.start_at, c.sort_order, c.id))

        return Response({
            "status": True,
            "server_now": now.isoformat(),
            "data": [campaign_public_dict(c, request, now) for c in live + upcoming],
        })


class CampaignDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        now = timezone.now()
        campaign = Campaign.objects.filter(slug=slug).first()
        status_name = get_campaign_status(campaign, now) if campaign else None

        if campaign is None or status_name == CAMPAIGN_STATUS.DRAFT:
            return Response(
                {"status": False, "code": "not_found", "message": "Campaign not found.", "server_now": now.isoformat()},
                status=404,
            )
        if status_name == CAMPAIGN_STATUS.ENDED:
            return Response(
                {
                    "status": False,
                    "code": "campaign_ended",
                    "message": "This campaign has ended. Thank you for being with us - please check our other offers.",
                    "server_now": now.isoformat(),
                },
                status=410,
            )

        payload = {"campaign": campaign_detail_dict(campaign, request, now), "products": []}
        if status_name == CAMPAIGN_STATUS.LIVE:
            payload["products"] = self._live_products(request, campaign)
        return Response({"status": True, "data": payload})

    @staticmethod
    def _live_products(request, campaign):
        rows = list(
            CampaignProduct.objects
            .filter(
                campaign=campaign,
                is_active=True,
                product__status=CATEGORY_PRODUCT_STATUS.ACTIVE,
                product__is_gift_only=False,
            )
            .select_related("product", "product__category")
            .prefetch_related(
                "variant_discounts",
                "product__variants",
                "product__images",
                Prefetch("product__gift_product", queryset=ProductGifting.objects.select_related("gift_product")),
            )
            .order_by("sort_order", "id")
        )
        sold_map = get_sold_units_map(rows)

        products = []
        for row in rows:
            p = row.product
            switches = effective_switches(campaign, row)
            item = {
                "id": p.id,
                "slug": p.slug,
                "name": p.name,
                **_listing_price_fields(p),
                "image": primary_image_url(p),
                "has_variants": p.has_variants,
                "category": {
                    "id": p.category.id if p.category else None,
                    "name": p.category.name if p.category else "",
                },
                "last_update_at": p.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "campaign_pricing": build_campaign_pricing(campaign, row, p, sold_units=sold_map[row.id]),
            }
            item.update(gift_fields(p, switches, request, gifts=list(p.gift_product.all())))
            products.append(item)
        return products
