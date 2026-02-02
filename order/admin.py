from django.contrib import admin
from .models import PaymentMethod, Address, Order, OrderItem, Shipment, Payment, Review

admin.site.register(PaymentMethod)
admin.site.register(Address)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Shipment)
admin.site.register(Payment)
admin.site.register(Review)