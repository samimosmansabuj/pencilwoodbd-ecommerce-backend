from django.contrib import admin
from .models import OrderAttempt, PaymentMethod, Address, Order, OrderItem, OrderRequest, Shipment, Payment, Review, TelegramBotConfig, SteadFastWebhookLog, OrderActivityLog
from django_json_widget.widgets import JSONEditorWidget
from django.db import models

# class OrderAdmin(admin.ModelAdmin):
#     formfield_overrides = {
#         models.JSONField: {'widget': JSONEditorWidget},  # <-- JSONField er jonno widget
#     }

@admin.register(OrderAttempt)
class OrderAttemptAdmin(admin.ModelAdmin):
    list_display = ("phone", "name", "district", "created_at", "updated_at")
    search_fields = ("phone", "name")
    ordering = ("-updated_at",)

@admin.register(TelegramBotConfig)
class TelegramBotConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "group_chat_id", "is_active", "notify_sources", "updated_at")


@admin.register(OrderActivityLog)
class OrderActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "order", "order_request", "user", "created_at")
    list_filter = ("user",)
    ordering = ("-created_at",)

admin.site.register(PaymentMethod)
admin.site.register(Address)
# admin.site.register(Order, OrderAdmin)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Shipment)
admin.site.register(Payment)
admin.site.register(Review)
admin.site.register(SteadFastWebhookLog)


@admin.register(OrderRequest)
class OrderRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "created_by", "created_at", "total_cost", "status",
                    "token_short", "form_open", "created_from")
    list_filter = ("created_by", "status", "created_at")
    search_fields = ("id", "customer__name", "customer__phone", "submit_token")
    readonly_fields = ("submit_token", "created_at", "updated_at")
    list_select_related = ("customer", "created_by")
    date_hierarchy = "created_at"
    ordering = ("-id",)

    @admin.display(description="Form token")
    def token_short(self, obj):
        return str(obj.submit_token)[:8] if obj.submit_token else "- (none)"

    @admin.display(description="Form open")
    def form_open(self, obj):
        sec = ((obj.metadata or {}).get("created_audit") or {}).get("form_open_seconds")
        if sec is None:
            return "-"
        return f"{sec}s" if sec < 90 else (f"{sec // 60}m" if sec < 5400 else f"{sec // 3600}h {(sec % 3600) // 60}m")

    @admin.display(description="Created from")
    def created_from(self, obj):
        a = (obj.metadata or {}).get("created_audit") or {}
        return f"{a.get('device', '-')} | {a.get('ip', '-')}" if a else "-"