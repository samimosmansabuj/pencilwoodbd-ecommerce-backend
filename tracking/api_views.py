from datetime import timedelta

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import VisitorProfile, ActivityEvent
from .serializers import TrackBatchSerializer
from product.models import Product


def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class TrackEventAPIView(APIView):
    
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TrackBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ip = get_client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")
        customer = getattr(request.user, "customer_profile", None) if request.user.is_authenticated else None

        visitor, created = VisitorProfile.objects.get_or_create(
            visitor_id=data["visitor_id"],
            defaults={
                "first_ip": ip,
                "utm_source": data.get("utm_source"),
                "utm_medium": data.get("utm_medium"),
                "utm_campaign": data.get("utm_campaign"),
                "landing_url": data.get("landing_url"),
                "referrer": data.get("referrer"),
            },
        )

        if customer and visitor.customer_id != customer.id:
            visitor.customer = customer
            ActivityEvent.objects.filter(visitor=visitor, customer__isnull=True).update(customer=customer)

        visitor.last_ip = ip
        visitor.user_agent = ua
        if visitor.last_seen and (timezone.now() - visitor.last_seen) > timedelta(minutes=30):
            visitor.total_visits += 1
        elif created:
            visitor.total_visits = 1
        visitor.save()

        events_payload = data["events"]
        product_ids = {ev["product_id"] for ev in events_payload if ev.get("product_id")}
        products_by_id = Product.objects.in_bulk(product_ids) if product_ids else {}

        events_to_create = [
            ActivityEvent(
                visitor=visitor,
                customer=visitor.customer,
                event_type=ev.get("event_type"),
                page_url=(ev.get("page_url") or "")[:500],
                page_title=(ev.get("page_title") or "")[:255],
                referrer=ev.get("referrer"),
                product=products_by_id.get(ev.get("product_id")),
                meta=ev.get("meta") or {},
                ip_address=ip,
            )
            for ev in events_payload
        ]
        ActivityEvent.objects.bulk_create(events_to_create)

        page_view_count = sum(1 for ev in events_payload if ev.get("event_type") == "page_view")
        if page_view_count:
            visitor.total_page_views += page_view_count
            visitor.save(update_fields=["total_page_views"])

        return Response({"status": True, "visitor_id": str(visitor.visitor_id)})


class IdentifyVisitorAPIView(APIView):
    
    permission_classes = [AllowAny]

    def post(self, request):
        visitor_id = request.data.get("visitor_id")
        if not visitor_id:
            return Response({"status": False, "message": "visitor_id required"}, status=400)
        if not request.user.is_authenticated:
            return Response({"status": False, "message": "Login required"}, status=401)

        customer = getattr(request.user, "customer_profile", None)
        if not customer:
            return Response({"status": False, "message": "No customer profile found for this user"}, status=400)

        visitor, _ = VisitorProfile.objects.get_or_create(
            visitor_id=visitor_id, defaults={"customer": customer}
        )
        if visitor.customer_id != customer.id:
            visitor.customer = customer
            visitor.save(update_fields=["customer"])

        ActivityEvent.objects.filter(visitor=visitor, customer__isnull=True).update(customer=customer)

        return Response({"status": True})
