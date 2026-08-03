from django.urls import path
from .views import FacebookPixelSettingsView, TrackingSettingsView, log_marketing_event

# from .views import get_tracking_settings

urlpatterns = [
    path("api/pixel-settings/", FacebookPixelSettingsView.as_view(), name="pixel-settings"),
    path("api/tracking-settings/", TrackingSettingsView.as_view(), name="tracking-settings"),
    path("api/marketing/log-event/", log_marketing_event, name="log-marketing-event"),
]
