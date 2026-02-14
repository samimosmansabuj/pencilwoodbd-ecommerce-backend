from django.urls import path
from .api_views import DeliveryOptionListAPIView, OrderCreateAPIView, ShipmentSerializerAPIView

urlpatterns = [
    
    
    
    
    
    path('api/create-order/', OrderCreateAPIView.as_view(), name="create-order"),
    path('api/v1/delivery-options/', DeliveryOptionListAPIView.as_view(), name="delivery-options"),
    path('api/v1/shipment-info/<int:order_id>/', ShipmentSerializerAPIView.as_view(), name="shipment-info"),
]