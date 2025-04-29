from django.urls import path
from .views import FacebookPixelSettingsView
# from .views import get_tracking_settings

urlpatterns = [
    path("api/pixel-settings/", FacebookPixelSettingsView.as_view(), name="get_facebook_pixel_settings"),
    # path("api/tracking-settings/", get_tracking_settings, name="get_tracking_settings"),
]
