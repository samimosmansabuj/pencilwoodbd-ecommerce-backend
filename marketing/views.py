from rest_framework.decorators import api_view
from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from .models import MarketingEventLog, MarketingIntegration, EmailConfig
from pencilwoodbd.choices import MarketingIntegrationProviderChoices, MarketingIntegrationStatusChoices

class FacebookPixelSettingsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    def get(self, request):
        try:
            facebook_pixel = MarketingIntegration.objects.filter(
                provider=MarketingIntegrationProviderChoices.facebook_pixel, status=MarketingIntegrationStatusChoices.ACTIVE
            ).first()
            FACEBOOK_PIXEL_ID = facebook_pixel.config["pixel_id"] if facebook_pixel and facebook_pixel.config else None
            return Response(
                {
                    'FACEBOOK_PIXEL_ID': FACEBOOK_PIXEL_ID,
                }
            )
        except Exception as e:
            return Response({'error': str(e)}, status=500)

