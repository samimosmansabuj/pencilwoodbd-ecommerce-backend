from django.urls import path
from .api_views import (
    DeliveryOptionListAPIView, 
     
    ShipmentSerializerAPIView, 
    OrderListAPIView, 
    OrderDetailAPIView,
    CheckoutSummaryAPIView, 
    PlaceOrderAPIView,
    # SteadfastWebhookView,
)

from .webhook_views import SteadfastWebhookAPIView
from .views import (
    AddOrderView, OrderView, OrderDetailView, OrderUpdateView, OrderDeleteView,
    OrderDeliveryOptionSubmitView, OrderInvoiceView, update_order, OrderStatusUpdateView,
    OrderBulkActionView,
    AddOrderRequestView, OrderRequestListView, OrderRequestDetailView,
    ApproveOrderRequestView, RejectOrderRequestView, UpdateOrderRequestWorkStatusView,
    OrderRequestStatusUpdateView,
    TelegramBotSettingsView, delete_telegram_bot_config, toggle_telegram_bot_active,
    OrderTokenPrintView, OrderBulkTokenPrintView, OrderPathaoParcelSubmitView,
    OrderUrgentToggleView,
)

urlpatterns = [
    
    path('api/checkout/summary/', CheckoutSummaryAPIView.as_view(), name="checkout_summary"),
    path('api/checkout/place-order/', PlaceOrderAPIView.as_view(), name="place_order"),
    # path('api/order/create/', EcomOrderCreateAPIView.as_view(), name='order_create'),
    path('api/order/my-orders/', OrderListAPIView.as_view(), name='my_orders'),
    path('api/order/<str:order_id>/', OrderDetailAPIView.as_view(), name='order_detail_api'),
    
    
    path('api/v1/delivery-options/', DeliveryOptionListAPIView.as_view(), name="delivery-options"),
    path('api/v1/shipment-info/<int:order_id>/', ShipmentSerializerAPIView.as_view(), name="shipment-info"),
    
    path('webhook/steadfast/', SteadfastWebhookAPIView.as_view(), name='steadfast_webhook'),

    # ----------------- Dashboard: Orders -----------------
    path("orders/add/", AddOrderView.as_view(), name="add_order"),
    path('order-list/', OrderView.as_view(), name='order_list'),
    path('order-detail/<int:id>/', OrderDetailView.as_view(), name='order_detail'),
    path('order-detail/<int:pk>/update/', OrderUpdateView.as_view(), name='order_update_full'),
    path('orders/delete/<int:pk>/', OrderDeleteView.as_view(), name='order_delete'),
    path('orders/delivery-option-submit/<int:pk>/', OrderDeliveryOptionSubmitView.as_view(), name='order_delivery_option_submit'),
    path('orders/<int:id>/invoice/', OrderInvoiceView.as_view(), name='order_invoice'),
    path('order-detail/<int:order_id>/update/', update_order, name='order_update'),
    path('orders/<int:pk>/update-status/', OrderStatusUpdateView.as_view(), name='order_status_update'),
    path('orders/bulk-action/', OrderBulkActionView.as_view(), name='order_bulk_action'),

    # ----------------- Dashboard: Order Requests -----------------
    path("order-requests/add/", AddOrderRequestView.as_view(), name="add_order_request"),
    path("order-requests/<int:pk>/edit/", AddOrderRequestView.as_view(), name="edit_order_request"),
    path("order-request/", OrderRequestListView.as_view(), name="order_request_list"),
    path("order-request/<int:id>/", OrderRequestDetailView.as_view(), name="order_request_detail"),
    path("order-request/<int:pk>/approve/", ApproveOrderRequestView.as_view(), name="approve_order_request"),
    path("order-request/<int:pk>/reject/", RejectOrderRequestView.as_view(), name="reject_order_request"),
    path("order-request/<int:pk>/work-status/", UpdateOrderRequestWorkStatusView.as_view(), name="update_order_request_work_status"),
    path('order-request/<int:pk>/update-status/', OrderRequestStatusUpdateView.as_view(), name='order_request_status_update'),

    # ----------------- Dashboard: Telegram Bot Settings -----------------
    path('settings/telegram-bot/', TelegramBotSettingsView.as_view(), name='telegram_bot_settings'),
    path('settings/telegram-bot/delete/<int:id>/', delete_telegram_bot_config, name='delete_telegram_bot_config'),
    path('settings/telegram-bot/toggle/<int:id>/', toggle_telegram_bot_active, name='toggle_telegram_bot_active'),

    # ----------------- Dashboard: Token / Courier -----------------
    path('orders/<int:pk>/token-print/', OrderTokenPrintView.as_view(), name='order_token_print'),
    path('orders/bulk-token-print/', OrderBulkTokenPrintView.as_view(), name='order_bulk_token_print'),
    path('orders/<int:pk>/pathao-submit/', OrderPathaoParcelSubmitView.as_view(), name='order_pathao_submit'),
    path('orders/<int:pk>/toggle-urgent/', OrderUrgentToggleView.as_view(), name='order_toggle_urgent'),
]