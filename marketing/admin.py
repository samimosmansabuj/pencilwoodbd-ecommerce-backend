from django.contrib import admin
from .models import MarketingIntegration, MarketingEventLog, EmailConfig, UTMLink, Coupon, CouponUsage

admin.site.register(MarketingIntegration)
admin.site.register(MarketingEventLog)
admin.site.register(EmailConfig)

@admin.register(UTMLink)
class UTMLinkAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'platform', 'medium', 'destination_url', 'created_at')
    search_fields = ('campaign', 'platform', 'destination_url')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'is_active', 'max_uses_per_phone', 'start_date', 'end_date')
    filter_horizontal = ('applicable_landing_pages', 'applicable_products')
    search_fields = ('code',)

@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'phone', 'order', 'discount_applied', 'created_at')
    search_fields = ('phone', 'coupon__code')