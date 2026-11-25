from django.contrib import admin

from .models import Campaign, CampaignProduct, CampaignProductVariant


class CampaignProductInline(admin.TabularInline):
    model = CampaignProduct
    extra = 0
    raw_id_fields = ("product",)
    fields = ("product", "is_active", "sort_order", "discount_type", "discount_value", "variant_mode",
              "stock_limit", "gift_mode", "offer_mode")
    show_change_link = True


class CampaignProductVariantInline(admin.TabularInline):
    model = CampaignProductVariant
    extra = 0
    raw_id_fields = ("variant",)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "status_display", "start_at", "end_at", "is_active", "show_on_home", "sort_order")
    list_filter = ("is_active", "show_on_home", "allow_overlap", "allow_coupon")
    search_fields = ("title", "slug")
    readonly_fields = ("created_by", "created_at", "updated_at")
    inlines = [CampaignProductInline]
    fieldsets = (
        ("Basics", {"fields": ("title", "slug", "short_description", "sort_order", "show_on_home", "show_in_slider", "is_active")}),
        ("Schedule (Asia/Dhaka)", {"fields": ("start_at", "end_at")}),
        ("Look", {"fields": ("thumbnail", "banner_desktop", "banner_mobile",
                             "hero_title", "hero_subtitle", "hero_button_text")}),
        ("Pricing", {"fields": ("discount_base", "strike_price_display", "badge_mode", "badge_label", "price_surfaces")}),
        ("Rules", {"fields": ("allow_overlap", "allow_coupon")}),
        ("Gifts & offers", {
            "fields": ("include_product_gifts", "include_offers"),
            "description": "OFF by default. When off, campaign items get no free gift and do not count toward "
                           "buy-X-get-Y offers. Each product can override this.",
        }),
        ("Delivery", {"fields": ("delivery_mode", "delivery_amount_source", "delivery_config",
                                 "delivery_basis", "mixed_cart_delivery")}),
        ("Meta", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    @admin.display(description="Status")
    def status_display(self, obj):
        return obj.status

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CampaignProduct)
class CampaignProductAdmin(admin.ModelAdmin):
    list_display = ("campaign", "product", "is_active", "discount_type", "discount_value", "variant_mode", "stock_limit")
    list_filter = ("campaign", "is_active", "variant_mode")
    raw_id_fields = ("product",)
    inlines = [CampaignProductVariantInline]
