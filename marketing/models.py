from django.db import models

class FacebookPixel(models.Model):
    pixel_id = models.CharField(max_length=255, help_text="Your Facebook Pixel ID")
    access_token = models.CharField(max_length=255, blank=True, help_text="Your Businuess Manager Access Token")
    is_active = models.BooleanField(default=True, help_text="Enable or disable Pixel tracking")
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.is_active:
            FacebookPixel.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Facebook Pixel: - {self.pixel_id}"


# class TrackingSettings(models.Model):
#     # Facebook
#     fb_pixel_id = models.CharField(max_length=100, blank=True)
#     fb_access_token = models.CharField(max_length=255, blank=True)
#     fb_capi_enabled = models.BooleanField(default=False)

#     # Google
#     gtm_container_id = models.CharField(max_length=100, blank=True)
#     ga4_measurement_id = models.CharField(max_length=100, blank=True)
#     ga4_api_secret = models.CharField(max_length=100, blank=True)
#     ga4_enabled = models.BooleanField(default=False)

#     # Global
#     is_active = models.BooleanField(default=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     def save(self, *args, **kwargs):
#         if self.is_active:
#             TrackingSettings.objects.exclude(pk=self.pk).update(is_active=False)
#         super().save(*args, **kwargs)

#     def __str__(self):
#         return "Tracking Settings"


