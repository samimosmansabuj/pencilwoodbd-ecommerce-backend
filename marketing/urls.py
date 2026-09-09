from django.urls import path
from .views import (
    FacebookPixelSettingsView, TrackingSettingsView, log_marketing_event,
    PixelSettingsView, UTMLinkGeneratorView, TrafficSourceReportView,
    CouponSettingsView, delete_coupon, toggle_coupon_active, coupon_usage_log,
)

# from .views import get_tracking_settings

urlpatterns = [
    path("api/pixel-settings/", FacebookPixelSettingsView.as_view(), name="pixel-settings"),
    path("api/tracking-settings/", TrackingSettingsView.as_view(), name="tracking-settings"),
    path("api/marketing/log-event/", log_marketing_event, name="log-marketing-event"),

    # ----------------- Dashboard: Pixel -----------------
    path('settings/pixel/', PixelSettingsView.as_view(), name='pixel_settings'),

    # ----------------- Dashboard: Marketing reports -----------------
    path('marketing/utm-link-generator/', UTMLinkGeneratorView.as_view(), name='utm_link_generator'),
    path('marketing/traffic-source-report/', TrafficSourceReportView.as_view(), name='traffic_source_report'),

    # ----------------- Dashboard: Coupon -----------------
    path('settings/coupon/', CouponSettingsView.as_view(), name='coupon_settings'),
    path('settings/coupon/delete/<int:id>/', delete_coupon, name='delete_coupon'),
    path('settings/coupon/toggle/<int:id>/', toggle_coupon_active, name='toggle_coupon_active'),
    path('settings/coupon/<int:id>/usage/', coupon_usage_log, name='coupon_usage_log'),
]
