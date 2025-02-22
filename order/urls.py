from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderItemViews, OrderViews, PaymentMethodViews, AddressViews, OrderCreateViews

router = DefaultRouter()
router.register(r'order-item', OrderItemViews, basename='order-item')
router.register(r'order', OrderViews, basename='order')
router.register(r'address', AddressViews, basename='address')
router.register(r'payment-method', PaymentMethodViews, basename='payment-method')

urlpatterns = [
    path('', include(router.urls)),
    path('order-create/', OrderCreateViews.as_view(), name='order-create')
]