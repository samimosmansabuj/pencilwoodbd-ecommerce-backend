from django.contrib import admin
from .models import PaymentMethod, Address, Order, OrderItem, OrderRequest, Shipment, Payment, Review
from django_json_widget.widgets import JSONEditorWidget
from django.db import models

# class OrderAdmin(admin.ModelAdmin):
#     formfield_overrides = {
#         models.JSONField: {'widget': JSONEditorWidget},  # <-- JSONField er jonno widget
#     }


admin.site.register(PaymentMethod)
admin.site.register(Address)
# admin.site.register(Order, OrderAdmin)
admin.site.register(Order)
admin.site.register(OrderRequest)
admin.site.register(OrderItem)
admin.site.register(Shipment)
admin.site.register(Payment)
admin.site.register(Review)