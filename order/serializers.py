from rest_framework import serializers
from .models import OrderItem, Order, PaymentMethod, Address
from django.db import transaction


class AddressSerializers(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'street_01', 'street_02', 'upazila', 'post_office', 'post_code', 'district', 'country']

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'customer', 'quantity', 'price', 'total_price']

class OrderListSerializers(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True, read_only=True)
    address = AddressSerializers(read_only=True)
    class Meta:
        model = Order
        fields = '__all__'

class OrderSerializers(serializers.ModelSerializer):
    existing_address = serializers.PrimaryKeyRelatedField(queryset=Address.objects.none(), required=False)
    street = serializers.CharField(required=False)
    upazila = serializers.CharField(required=False)
    district = serializers.CharField(required=False)
    address = AddressSerializers(read_only=True)
    name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'order_items', 'total_cost', 'payment_type', 'payment_status', 'status', 'tracking_id', 'payment_method', 'address', 'name', 'phone_number',
            
            'existing_address', 'street', 'upazila', 'district'
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            self.fields['existing_address'].queryset = Address.objects.filter(customer=request.user.customer_authentication)

class PaymentMethodSerializers(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = '__all__'






class OrderItemCreateSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    class Meta:
        model = OrderItem
        fields = [
            "product_id",
            "quantity",
        ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemCreateSerializer(many=True, write_only=True)

    class Meta:
        model = Order
        fields = [
            "customer",
            "shipping_address",
            "delivery_type",
            "delivery_date",
            "payment_type",
            "items",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items")

        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            
            for item in items_data:
                product = Product.objects.get(id=item["product_id"])

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=item["quantity"],
                    price=product.current_price,
                    discount_price=product.discount_price,
                )

            # totals
            order.total_cost = (
                order.get_discount_total +
                order.shipping_total +
                order.tax_total
            )
            order.save()

        return order


