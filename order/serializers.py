from rest_framework import serializers
from site_app.models import DeliveryOption
from order.models import Shipment

class DeliveryOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryOption
        fields = "__all__"

class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = ["id", "courier", "tracking_number", "status", "label_url", "created_at", "updated_at"]
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.courier:
            courier_name = instance.courier.name
            courier_type = instance.courier.type if instance.courier.type else None
            courier = f"{courier_name} ({courier_type})" if courier_name and courier_type else courier_name or courier_type or None
            representation['courier'] = courier
        else:
            representation['courier'] = None
        return representation

