from django.contrib import admin
from .models import MarketingIntegration, MarketingEventLog, EmailConfig, UTMLink

admin.site.register(MarketingIntegration)
admin.site.register(MarketingEventLog)
admin.site.register(EmailConfig)

@admin.register(UTMLink)
class UTMLinkAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'platform', 'medium', 'destination_url', 'created_at')
    search_fields = ('campaign', 'platform', 'destination_url')