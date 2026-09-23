from rest_framework import serializers
from .models import EVENT_TYPE


class EventInputSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=EVENT_TYPE.choices, default=EVENT_TYPE.PAGE_VIEW)
    page_url = serializers.CharField(max_length=500, required=False, allow_blank=True)
    page_title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    referrer = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    meta = serializers.DictField(required=False)
    occurred_at = serializers.CharField(required=False, allow_blank=True)


class TrackBatchSerializer(serializers.Serializer):
    visitor_id = serializers.UUIDField()
    utm_source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    utm_medium = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    utm_campaign = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    landing_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    referrer = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    events = EventInputSerializer(many=True)
