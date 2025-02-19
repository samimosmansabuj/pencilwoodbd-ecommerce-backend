from rest_framework import serializers
from .models import OrderItem, Order, PaymentMethod, Address

class OrderItemSerializers(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = '__all__'


class OrderSerializers(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'


class PaymentMethodSerializers(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = '__all__'


class AddressSerializers(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'

