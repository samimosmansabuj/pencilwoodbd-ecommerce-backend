from django.urls import path
from .api_views import (
    DeliveryOptionListAPIView, 
    OrderCreateAPIView, 
    ShipmentSerializerAPIView, 
    OrderListAPIView, 
    OrderDetailAPIView,
    CheckoutSummaryAPIView, 
    PlaceOrderAPIView,
)

urlpatterns = [
    
    path('api/checkout/summary/', CheckoutSummaryAPIView.as_view(), name="checkout_summary"),
    path('api/checkout/place-order/', PlaceOrderAPIView.as_view(), name="place_order"),
    # path('api/order/create/', EcomOrderCreateAPIView.as_view(), name='order_create'),
    path('api/order/my-orders/', OrderListAPIView.as_view(), name='my_orders'),
    path('api/order/<str:order_id>/', OrderDetailAPIView.as_view(), name='order_detail'),
    
    
    path('api/create-order/', OrderCreateAPIView.as_view(), name="create-order"),
    path('api/v1/delivery-options/', DeliveryOptionListAPIView.as_view(), name="delivery-options"),
    path('api/v1/shipment-info/<int:order_id>/', ShipmentSerializerAPIView.as_view(), name="shipment-info"),
]