from rest_framework import serializers
from site_app.models import DeliveryOption

class DeliveryOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryOption
        fields = "__all__"
