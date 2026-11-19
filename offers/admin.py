from django.contrib import admin
from django.utils import timezone

from .models import Offer, OfferTier, OfferGift, ProductComboPair


class OfferTierInline(admin.TabularInline):
    model = OfferTier
    extra = 1
    fields = ("buy_qty", "free_qty")
    ordering = ("buy_qty",)


class OfferGiftInline(admin.TabularInline):
    model = OfferGift
    extra = 1
    fields = ("product", "variant", "tier", "quantity", "position")
    raw_id_fields = ("product", "variant")
    ordering = ("position", "id")

    def get_formset(self, request, obj=None, **kwargs):
        request._offer_obj = obj
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tier":
            offer = getattr(request, "_offer_obj", None)
            kwargs["queryset"] = OfferTier.objects.filter(offer=offer) if offer else OfferTier.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "rules", "count_mode", "gift_mode", "priority", "start_at", "end_at", "is_active")
    list_display_links = ("id", "name")
    list_filter = ("is_active", "gift_mode", "count_mode", "repeat", "apply_to_all")
    list_editable = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("-id",)
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("trigger_products", "trigger_categories")
    inlines = (OfferTierInline, OfferGiftInline)
    fieldsets = (
        ("Basic", {"fields": ("name", "description", "is_active", "priority", "start_at", "end_at")}),
        ("Counting & free items", {"fields": ("count_mode", "gift_mode", "require_selection", "repeat", "max_free_per_order")}),
        ("Applies to", {"fields": ("apply_to_all", "trigger_products", "trigger_categories")}),
        ("Info", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tiers")

    @admin.display(description="Status")
    def status(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return "Inactive"
        if obj.start_at and obj.start_at > now:
            return "Scheduled"
        if obj.end_at and obj.end_at < now:
            return "Ended"
        return "Running"

    @admin.display(description="Rules")
    def rules(self, obj):
        return ", ".join(f"Buy {t.buy_qty} \u2192 Free {t.free_qty}" for t in obj.tiers.all()) or "-"


@admin.register(ProductComboPair)
class ProductComboPairAdmin(admin.ModelAdmin):
    list_display = ("id", "product_a", "product_b", "created_at")
    raw_id_fields = ("product_a", "product_b")
