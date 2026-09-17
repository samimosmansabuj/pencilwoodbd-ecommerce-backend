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
admin.site.register(OrderRequest)
admin.site.register(OrderItem)
admin.site.register(Shipment)
admin.site.register(Payment)
admin.site.register(Review)
admin.site.register(SteadFastWebhookLog)
