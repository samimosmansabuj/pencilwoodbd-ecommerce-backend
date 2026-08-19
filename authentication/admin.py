from django.contrib import admin
from .models import Customer, CustomUser, Role, OrderTrackRecord, BlockedIdentity, TrackSettings
from django.contrib.sessions.models import Session
from django.contrib.auth.admin import UserAdmin

# admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(CustomUser)
admin.site.register(Customer)
admin.site.register(Role)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ["session_key", "get_decoded_data", "expire_date"]
    search_fields = ["session_key"]
    ordering = ["-expire_date"]

    def get_decoded_data(self, obj):
        """Display decoded session data in the admin panel."""
        return obj.get_decoded()

    get_decoded_data.short_description = "Session Data"


# ============ IP / DEVICE ORDER TRACKING & BLOCKING ============

@admin.register(OrderTrackRecord)
class OrderTrackRecordAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "ip_address", "device_hash_short", "status_at_capture", "created_at"]
    list_filter = ["status_at_capture", "created_at"]
    search_fields = ["ip_address", "device_hash", "order__order_id", "user_agent"]
    readonly_fields = ["order", "ip_address", "device_hash", "user_agent", "status_at_capture", "created_at"]
    ordering = ["-created_at"]

    def device_hash_short(self, obj):
        return obj.device_hash[:12] + "..."
    device_hash_short.short_description = "Device Hash"

    def has_add_permission(self, request):
        return False


@admin.register(BlockedIdentity)
class BlockedIdentityAdmin(admin.ModelAdmin):
    list_display = ["id", "ip_address", "device_hash_short", "reason", "is_active", "cancel_count_at_block_time", "blocked_at", "blocked_by", "unblocked_at", "unblocked_by"]
    list_filter = ["is_active", "reason", "blocked_at"]
    search_fields = ["ip_address", "device_hash", "note"]
    ordering = ["-blocked_at"]

    def device_hash_short(self, obj):
        return (obj.device_hash[:12] + "...") if obj.device_hash else "-"
    device_hash_short.short_description = "Device Hash"


@admin.register(TrackSettings)
class TrackSettingsAdmin(admin.ModelAdmin):
    list_display = ["mode", "cancel_threshold", "is_auto_block_enabled", "updated_at"]

    def has_add_permission(self, request):
        return not TrackSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False