from rest_framework.decorators import api_view
from rest_framework.views import APIView
from django.http import JsonResponse
from rest_framework.response import Response
from .models import FacebookPixel

# @api_view(['GET'])
# def get_facebook_pixel_settings(request):
#     try:
#         facebook_marketing = FacebookPixel.objects.filter(is_active=True).first()
#         return Response(
#             {
#                 'pixel_id': facebook_marketing.pixel_id or None,
#                 'access_token': facebook_marketing.access_token or None,
#             }
#         )
#     except Exception as e:
#         return Response({'error': str(e)}, status=500)


class FacebookPixelSettingsView(APIView):
    queryset = FacebookPixel.objects.filter(is_active=True)
    
    def get(self, request):
        try:
            facebook_marketing = FacebookPixel.objects.filter(is_active=True).first()
            return Response(
                {
                    'pixel_id': facebook_marketing.pixel_id or None,
                    'access_token': facebook_marketing.access_token or None,
                }
            )
        except Exception as e:
            return Response({'error': str(e)}, status=500)



# utils/facebook_conversion.py
import requests
import uuid
from django.conf import settings

def send_facebook_event(event_name, user_data, custom_data):
    facebook_marketing = FacebookPixel.objects.filter(is_active=True).first()
    pixel_id = facebook_marketing.pixel_id or None
    access_token = facebook_marketing.access_token or None

    url = f'https://graph.facebook.com/v19.0/{pixel_id}/events'

    payload = {
        'data': [
            {
                'event_name': event_name,
                'event_time': int(uuid.uuid1().time >> 64),
                'event_id': str(uuid.uuid4()),
                'user_data': user_data,
                'custom_data': custom_data,
                'action_source': 'website',
            }
        ],
        'access_token': access_token
    }

    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        return {'error': str(e)}


def order_success(request):
    user_data = {
        'em': ['sha256hashedemail'],  # hashed email (sha256)
        'ph': ['sha256hashedphone'],
        'client_user_agent': request.META.get('HTTP_USER_AGENT'),
        'ip_address': request.META.get('REMOTE_ADDR'),
    }

    # Custom Data
    custom_data = {
        'currency': 'USD',
        'value': 99.99,
        'content_ids': ['prod123'],
        'content_type': 'product'
    }

    send_facebook_event('Purchase', user_data, custom_data)

    return JsonResponse({'message': 'Order Success'})

import hashlib

def hash_user_data(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


# 
# from .models import TrackingSettings

# def get_tracking_settings(request):
#     settings = TrackingSettings.objects.filter(is_active=True).first()
#     if settings:
#         return JsonResponse({
#             "fb_pixel_id": settings.fb_pixel_id,
#             "gtm_container_id": settings.gtm_container_id,
#             "ga4_measurement_id": settings.ga4_measurement_id,
#             "ga4_enabled": settings.ga4_enabled,
#         })
#     return JsonResponse({}, status=404)

