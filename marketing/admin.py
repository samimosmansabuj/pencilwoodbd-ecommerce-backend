from django.contrib import admin
from .models import FacebookPixel

@admin.register(FacebookPixel)
class FacebookPixelAdmin(admin.ModelAdmin):
    list_display = ("pixel_id", "access_token", "is_active", "updated_at")
    readonly_fields = ("updated_at",)


# from .models import TrackingSettings

# @admin.register(TrackingSettings)
# class TrackingSettingsAdmin(admin.ModelAdmin):
#     list_display = ("fb_pixel_id", "gtm_container_id", "ga4_measurement_id", "is_active", "updated_at")
#     readonly_fields = ("updated_at",)


