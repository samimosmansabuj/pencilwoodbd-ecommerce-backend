from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from .models import MarketingEventLog, MarketingIntegration, EmailConfig, UTMLink, Coupon
from pencilwoodbd.choices import MarketingIntegrationProviderChoices, MarketingIntegrationStatusChoices, USER_TYPE, CATEGORY_PRODUCT_STATUS

from http import HTTPStatus
import json
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate



from order.models import Order
from product.models import Product
from site_app.models import LandingPageProduct

class FacebookPixelSettingsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        try:
            facebook_pixel = MarketingIntegration.objects.filter(
                provider=MarketingIntegrationProviderChoices.facebook_pixel,
                status=MarketingIntegrationStatusChoices.ACTIVE
            ).first()
            FACEBOOK_PIXEL_ID = facebook_pixel.config["pixel_id"] if facebook_pixel and facebook_pixel.config else None
            return Response({'FACEBOOK_PIXEL_ID': FACEBOOK_PIXEL_ID})
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class TrackingSettingsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            active_integrations = MarketingIntegration.objects.filter(
                status=MarketingIntegrationStatusChoices.ACTIVE
            )

            data = {
                "facebook_pixel": {"enabled": False, "pixel_id": None},
                "facebook_capi": {"enabled": False},
                "gtm": {"enabled": False, "container_id": None},
                "ga4": {"enabled": False, "measurement_id": None},
            }

            for integration in active_integrations:
                config = integration.config or {}

                if integration.provider == MarketingIntegrationProviderChoices.facebook_pixel:
                    pixel_id = config.get("pixel_id")
                    if pixel_id:
                        data["facebook_pixel"] = {"enabled": True, "pixel_id": pixel_id}

                elif integration.provider == MarketingIntegrationProviderChoices.facebook_capi:
                    data["facebook_capi"] = {"enabled": True}

                elif integration.provider == MarketingIntegrationProviderChoices.gtm:
                    container_id = config.get("container_id")
                    if container_id:
                        data["gtm"] = {"enabled": True, "container_id": container_id}

                elif integration.provider == MarketingIntegrationProviderChoices.ga4:
                    measurement_id = config.get("measurement_id")
                    if measurement_id:
                        data["ga4"] = {"enabled": True, "measurement_id": measurement_id}

            # ---- Per-product (E-commerce site) ----
            product_id = request.GET.get("product_id")
            if product_id:
                product = Product.objects.filter(id=product_id).only(
                    "id", "enable_pixel_tracking", "facebook_pixel_id",
                    "gtm_container_id", "ga4_measurement_id"
                ).first()
                if product:
                    if not product.enable_pixel_tracking:
                        data["facebook_pixel"]["enabled"] = False
                        data["facebook_capi"]["enabled"] = False
                        data["gtm"]["enabled"] = False
                        data["ga4"]["enabled"] = False
                    else:
                        if product.facebook_pixel_id:
                            data["facebook_pixel"] = {"enabled": True, "pixel_id": product.facebook_pixel_id}
                        if product.gtm_container_id:
                            data["gtm"] = {"enabled": True, "container_id": product.gtm_container_id}
                        if product.ga4_measurement_id:
                            data["ga4"] = {"enabled": True, "measurement_id": product.ga4_measurement_id}

            # ---- Per-landing-page  ----
            landing_code = request.GET.get("landing_code")
            if landing_code:
                landing = LandingPageProduct.objects.filter(code=landing_code).only(
                    "id", "enable_pixel_tracking", "facebook_pixel_id",
                    "gtm_container_id", "ga4_measurement_id"
                ).first()
                if landing:
                    if not landing.enable_pixel_tracking:
                        data["facebook_pixel"]["enabled"] = False
                        data["facebook_capi"]["enabled"] = False
                        data["gtm"]["enabled"] = False
                        data["ga4"]["enabled"] = False
                    else:
                        if landing.facebook_pixel_id:
                            data["facebook_pixel"] = {"enabled": True, "pixel_id": landing.facebook_pixel_id}
                        if landing.gtm_container_id:
                            data["gtm"] = {"enabled": True, "container_id": landing.gtm_container_id}
                        if landing.ga4_measurement_id:
                            data["ga4"] = {"enabled": True, "measurement_id": landing.ga4_measurement_id}

            return Response({"status": True, "data": data})
        except Exception as e:
            return Response({"status": False, "error": str(e)}, status=500)
        

@api_view(['POST'])
@permission_classes([AllowAny])
def log_marketing_event(request):
    try:
        event_name = request.data.get("event_name")
        payload = request.data.get("payload", {})
        if not event_name:
            return Response({"status": False, "error": "event_name is required"}, status=400)
        MarketingEventLog.objects.create(event_name=event_name, payload=payload)
        return Response({"status": True})
    except Exception as e:
        return Response({"status": False, "error": str(e)}, status=500)

# Dashboard (staff/admin) marketing views
class PixelSettingsView(LoginRequiredMixin, View):
    login_url = '/dashboard/login/'
    template_name = 'db_settings/pixel_settings.html'

    def get(self, request):
        if request.user.user_type != USER_TYPE.ADMIN:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('dashboard_home')

        providers = [
            MarketingIntegrationProviderChoices.facebook_pixel,
            MarketingIntegrationProviderChoices.facebook_capi,
            MarketingIntegrationProviderChoices.gtm,
            MarketingIntegrationProviderChoices.ga4,
        ]

        integrations = {}
        for provider in providers:
            obj, _ = MarketingIntegration.objects.get_or_create(
                provider=provider,
                defaults={"status": MarketingIntegrationStatusChoices.INACTIVE, "config": {}}
            )
            integrations[provider] = obj

        context = {"integrations": integrations}
        return render(request, self.template_name, context)

    def post(self, request):
        if request.user.user_type != USER_TYPE.ADMIN:
            messages.error(request, "You don't have permission to perform this action.")
            return redirect('dashboard_home')

        provider = request.POST.get("provider")
        is_active = request.POST.get("is_active") == "on"

        try:
            integration, _ = MarketingIntegration.objects.get_or_create(provider=provider)

            config = {}
            if provider == MarketingIntegrationProviderChoices.facebook_pixel:
                config = {"pixel_id": request.POST.get("pixel_id", "").strip()}
            elif provider == MarketingIntegrationProviderChoices.facebook_capi:
                config = {
                    "pixel_id": request.POST.get("capi_pixel_id", "").strip(),
                    "access_token": request.POST.get("capi_access_token", "").strip(),
                }
            elif provider == MarketingIntegrationProviderChoices.gtm:
                config = {"container_id": request.POST.get("container_id", "").strip()}
            elif provider == MarketingIntegrationProviderChoices.ga4:
                config = {"measurement_id": request.POST.get("measurement_id", "").strip()}

            integration.config = config
            integration.status = (
                MarketingIntegrationStatusChoices.ACTIVE if is_active
                else MarketingIntegrationStatusChoices.INACTIVE
            )
            integration.save()

            messages.success(request, f"{integration.get_provider_display()} settings updated successfully.")
        except Exception as e:
            messages.error(request, f"Failed to update settings: {str(e)}")

        return redirect('pixel_settings')
    


# ------------------Site Content: Footer Links--------


class UTMLinkGeneratorView(LoginRequiredMixin, View):
    login_url = '/dashboard/login/'
    template_name = 'db_settings/utm_generator.html'

    def get(self, request):
        links = UTMLink.objects.all()[:100]
        recent_urls = list(
            UTMLink.objects.order_by('-created_at')
            .values_list('destination_url', flat=True)
            .distinct()[:15]
        )
        context = {"links": links, "recent_urls": recent_urls}
        return render(request, self.template_name, context)

    def post(self, request):
        destination_url = request.POST.get("destination_url", "").strip()
        platform = request.POST.get("platform", "").strip()
        medium = request.POST.get("medium", "").strip()
        campaign = request.POST.get("campaign", "").strip()

        if not destination_url or not platform or not campaign:
            messages.error(request, "Destination URL, Platform, and Campaign name are required.")
            return redirect('utm_link_generator')

        parsed = urlparse(destination_url)
        query = parse_qs(parsed.query)
        query["utm_source"] = [platform]
        query["utm_medium"] = [medium or "paid_social"]
        query["utm_campaign"] = [campaign]

        new_query = urlencode({k: v[0] for k, v in query.items()})
        generated_url = urlunparse(parsed._replace(query=new_query))

        UTMLink.objects.create(
            destination_url=destination_url,
            platform=platform,
            medium=medium,
            campaign=campaign,
            generated_url=generated_url,
            created_by=request.user,
        )

        messages.success(request, "UTM link generated successfully.")
        return redirect('utm_link_generator')


# ------------------ Traffic Source Report --------------


class TrafficSourceReportView(LoginRequiredMixin, View):
    login_url = '/dashboard/login/'
    template_name = 'db_settings/traffic_source_report.html'

    def get(self, request):
        orders = Order.objects.exclude(utm_source__isnull=True).exclude(utm_source="")

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        if start_date:
            orders = orders.filter(created_at__date__gte=start_date)
        if end_date:
            orders = orders.filter(created_at__date__lte=end_date)

        # 1. Channel share (pie chart)
        channel_share = list(
            orders.values("utm_source")
            .annotate(order_count=Count("id"), revenue=Sum("total_cost"))
            .order_by("-order_count")
        )

        # 2. Revenue by campaign (bar chart/table)
        campaign_revenue = list(
            orders.exclude(utm_campaign__isnull=True).exclude(utm_campaign="")
            .values("utm_campaign", "utm_source")
            .annotate(order_count=Count("id"), revenue=Sum("total_cost"))
            .order_by("-revenue")
        )

        # 3. Trend over time (line chart) — daily order counts per channel
        trend = list(
            orders.annotate(day=TruncDate("created_at"))
            .values("day", "utm_source")
            .annotate(order_count=Count("id"))
            .order_by("day")
        )
        trend_serialized = [
            {"day": t["day"].isoformat(), "utm_source": t["utm_source"], "order_count": t["order_count"]}
            for t in trend
        ]

        context = {
            "channel_share": channel_share,
            "campaign_revenue": campaign_revenue,
            "trend_json": json.dumps(trend_serialized, default=str),
            "channel_share_json": json.dumps(channel_share, default=str),
        }
        return render(request, self.template_name, context)


# ----------------- Coppon -----------------


class CouponSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        coupons = Coupon.objects.all().order_by("-created_at")
        landing_pages = LandingPageProduct.objects.filter(is_active=True)
        products = Product.objects.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE)

        context = {
            "coupons": coupons,
            "landing_pages": landing_pages,
            "products": products,
        }
        return render(request, "db_settings/coupon_settings.html", context)

    def post(self, request):
        try:
            data = request.POST
            coupon_id = data.get("coupon_id")

            code = data.get("code", "").strip()
            discount_type = data.get("discount_type")
            discount_value = data.get("discount_value")
            max_discount_amount = data.get("max_discount_amount") or None
            min_order_amount = data.get("min_order_amount") or 0
            is_active = data.get("is_active") == "on"
            start_date = data.get("start_date") or None
            end_date = data.get("end_date") or None
            max_uses_per_phone = data.get("max_uses_per_phone") or 1
            total_usage_limit = data.get("total_usage_limit") or None

            landing_page_ids = data.getlist("applicable_landing_pages")
            product_ids = data.getlist("applicable_products")

            customer_condition = data.get("customer_condition", "ANY")
            min_previous_orders = data.get("min_previous_orders") or None
            order_history_scope = data.get("order_history_scope", "ALL_ORDERS")
            count_orders_before_coupon_creation = (
                data.get("count_orders_before_coupon_creation") == "on"
            )

            if not code or not discount_value:
                return JsonResponse(
                    {
                        "status": False,
                        "message": "Code and discount value are required.",
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )

            if not landing_page_ids and not product_ids:
                return JsonResponse(
                    {
                        "status": False,
                        "message": "Please select at least one Landing Page or Product.",
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )

            if coupon_id:
                coupon = get_object_or_404(Coupon, id=coupon_id)
            else:
                coupon = Coupon()

            coupon.code = code
            coupon.discount_type = discount_type
            coupon.discount_value = discount_value
            coupon.max_discount_amount = max_discount_amount
            coupon.min_order_amount = min_order_amount
            coupon.is_active = is_active
            coupon.start_date = start_date
            coupon.end_date = end_date
            coupon.max_uses_per_phone = max_uses_per_phone
            coupon.total_usage_limit = total_usage_limit
            coupon.customer_condition = customer_condition
            coupon.min_previous_orders = min_previous_orders
            coupon.order_history_scope = order_history_scope
            coupon.count_orders_before_coupon_creation = (
                count_orders_before_coupon_creation
            )

            coupon.save()

            coupon.applicable_landing_pages.set(landing_page_ids)
            coupon.applicable_products.set(product_ids)

            return JsonResponse(
                {
                    "status": True,
                    "message": "Coupon saved successfully.",
                },
                status=HTTPStatus.OK,
            )

        except Exception as e:
            return JsonResponse(
                {
                    "status": False,
                    "message": str(e),
                },
                status=HTTPStatus.BAD_REQUEST,
            )


@login_required(login_url="admin_login")
def delete_coupon(request, id):
    if request.method == "DELETE":
        try:
            coupon = get_object_or_404(Coupon, id=id)
            coupon.delete()
            return JsonResponse({"status": True, "message": "Coupon deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_coupon_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        coupon = get_object_or_404(Coupon, id=id)
        coupon.is_active = request.POST.get("is_active") == "true"
        coupon.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Status updated", "is_active": coupon.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def coupon_usage_log(request, id):
    coupon = get_object_or_404(Coupon, id=id)
    usages = coupon.usages.select_related("order").order_by("-created_at")
    context = {"coupon": coupon, "usages": usages}
    return render(request, "db_settings/partial/partial_coupon_usage_log.html", context)
