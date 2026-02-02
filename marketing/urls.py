from django.urls import path
from .views import FacebookPixelSettingsView
# from .views import get_tracking_settings

urlpatterns = [
    path("api/pixel-settings/", FacebookPixelSettingsView.as_view(), name="pixel-settings"),
]
