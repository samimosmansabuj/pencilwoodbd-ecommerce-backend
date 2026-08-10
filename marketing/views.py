from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from .models import MarketingEventLog, MarketingIntegration, EmailConfig
from pencilwoodbd.choices import MarketingIntegrationProviderChoices, MarketingIntegrationStatusChoices


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
                    # Server-side only — frontend just needs to know it's on
                    data["facebook_capi"] = {"enabled": True}

                elif integration.provider == MarketingIntegrationProviderChoices.gtm:
                    container_id = config.get("container_id")
                    if container_id:
                        data["gtm"] = {"enabled": True, "container_id": container_id}

                elif integration.provider == MarketingIntegrationProviderChoices.ga4:
                    measurement_id = config.get("measurement_id")
                    if measurement_id:
                        data["ga4"] = {"enabled": True, "measurement_id": measurement_id}

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