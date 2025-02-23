from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderItemViews, PaymentMethodViews, AddressViews, OrderCreateViews, OrderListViews

router = DefaultRouter()
router.register(r'order-item', OrderItemViews, basename='order-item')
router.register(r'order', OrderListViews, basename='order')
router.register(r'address', AddressViews, basename='address')
router.register(r'payment-method', PaymentMethodViews, basename='payment-method')

urlpatterns = [
    path('', include(router.urls)),
    path('order-create/', OrderCreateViews.as_view(), name='order-create'),
    # path('order/', OrderViews.as_view(), name='order'),
    # path('order/<int:pk>/', OrderViews.as_view(), name='order-retrive'),
]