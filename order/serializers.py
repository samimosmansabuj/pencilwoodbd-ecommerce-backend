from rest_framework import serializers
from .models import OrderItem, Order, PaymentMethod, Address

class AddressSerializers(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'street_01', 'street_02', 'upazila', 'post_office', 'post_code', 'district', 'country']

class OrderItemSerializers(serializers.ModelSerializer):
    # existing_address = serializers.PrimaryKeyRelatedField(required=False)
    existing_address = serializers.PrimaryKeyRelatedField(queryset=Address.objects.none(), required=False)
    street = serializers.CharField(required=False)
    upazila = serializers.CharField(required=False)
    district = serializers.CharField(required=False)
    address = AddressSerializers(read_only=True)
    class Meta:
        model = OrderItem
        fields = [
            'id', 'customer', 'order_items', 'total_cost', 'payment_type',
            'payment_status', 'status', 'tracking_id',
            'payment_method', 'address', 'existing_address', 'street', 'upazila', 'district'
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            self.fields['existing_address'].queryset = Address.objects.filter(customer=request.user.customer_authentication)
    
    def create(self, validated_data):
        order_items = validated_data.pop('order_items')
        validated_data['address'] = self.get_address(validated_data)
        order = Order.objects.create(**validated_data)
        total_cost = 0
        for item_data in order_items:
            order.order_items.add(item_data)
            total_cost += item_data.total_price
        order.total_cost = total_cost
        order.save()
        return order
    
    #Address Assign or Creation Start
    def get_address(validated_data, customer):
        customer = validated_data.get('customer')
        
        existing_addresses = validated_data.pop('existing_address', None)
        street_01 = validated_data.pop('street', None)
        upazila = validated_data.pop('upazila', None)
        district = validated_data.pop('district', None)
        if existing_addresses:
            address = existing_addresses
        elif street_01 and upazila and district:
            address = Address.objects.create(
                customer = customer,
                street_01 = street_01,
                upazila = upazila,
                district = district
            )
        else:
            raise serializers.ValidationError("Provide either a new address or select an existing one.")
        return address



class OrderSerializers(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'


class PaymentMethodSerializers(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = '__all__'




