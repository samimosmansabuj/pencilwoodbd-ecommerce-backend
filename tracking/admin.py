from django.contrib import admin
from .models import VisitorProfile, ActivityEvent


@admin.register(VisitorProfile)
class VisitorProfileAdmin(admin.ModelAdmin):
    list_display = ("visitor_id", "customer", "last_ip", "total_visits", "total_page_views", "first_seen", "last_seen")
    list_filter = ("last_seen",)
    search_fields = ("visitor_id", "customer__name", "customer__phone", "last_ip")
    autocomplete_fields = ("customer",)


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "customer", "visitor", "page_url", "product", "variant_label", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("customer__name", "page_url", "visitor__visitor_id", "product__name", "product__slug", "variant_label")
    autocomplete_fields = ("customer", "product", "visitor")
    raw_id_fields = ("variant",)
    date_hierarchy = "created_at"
