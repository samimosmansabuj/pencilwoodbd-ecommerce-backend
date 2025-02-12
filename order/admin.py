from django.contrib import admin
from .models import OrderItem, PaymentMethod, Address, Order

admin.site.register(OrderItem)
admin.site.register(Order)
admin.site.register(Address)
admin.site.register(PaymentMethod)