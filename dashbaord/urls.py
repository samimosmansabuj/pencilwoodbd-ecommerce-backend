from django.urls import path, include
from .views import *
from .api_views import *
from rest_framework.routers import DefaultRouter

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    
    path('admin-login/', UserLoginView.as_view(), name='admin_login'),
    path('admin-logout/', AdminLogoutView.as_view(), name='admin_logout'),
    

    path('users/', UserManagementView.as_view(), name='user_management'),
    path("users/staff/create/", StaffCreateView.as_view(), name="staff_create"),
    path("users/staff/<int:pk>/edit/", StaffUpdateView.as_view(), name="staff_update"),

    path('product-list/', ProductListView.as_view(), name='product_list'),
    path('product-add/', add_product, name='product_add'),
    path("product/update/<int:pk>/", product_update, name="product_update"),
    path('products/delete/<int:pk>/', ProductDeleteView.as_view(), name='product_delete'),  

    path('settings/delivery-charge/', DeliveryChargeSettingsView.as_view(), name='delivery_charge_settings'),

    # path('media-center/', product_list, name='media_center'),

    path('category-list/', CategoryView.as_view(), name='category_list'),
    # path('category-add/', add_category, name='category_add'),
    path('get-category/<int:id>/', get_category, name='get_category'),
    path('delete-category/<int:id>/', delete_category, name='delete_category'),

    path("orders/add/", AddOrderView.as_view(),name="add_order"),
    path('order-list/', OrderView.as_view(), name='order_list'),
    path('order-detail/<int:id>/', OrderDetailView.as_view(), name='order_detail'),
    path('order-detail/<int:pk>/update/', OrderUpdateView.as_view(), name='order_update_full'),
    path('orders/delete/<int:pk>/', OrderDeleteView.as_view(), name='order_delete'),
    path('orders/delivery-option-submit/<int:pk>/', OrderDeliveryOptionSubmitView.as_view(), name='order_delivery_option_submit'),
    path('orders/<int:id>/invoice/', OrderInvoiceView.as_view(), name='order_invoice'),
    path('order-detail/<int:order_id>/update/', update_order, name='order_update'),
    path('orders/<int:pk>/update-status/', OrderStatusUpdateView.as_view(), name='order_status_update'),
    path('orders/bulk-action/', OrderBulkActionView.as_view(), name='order_bulk_action'),

    # ----------------- Product Features ---------------------
    path('product/<int:product_id>/features/', ProductFeatureView.as_view(), name='product_features'),
    path('product-feature/delete/<int:id>/', delete_product_feature, name='delete_product_feature'),

    # ----------------- FAQ ---------------------
    path('faq-list/', FAQManagementView.as_view(), name='faq_list'),
    path('faq/delete/<int:id>/', delete_faq, name='delete_faq'),

    # ----------------- Reviews ---------------------
    path('review-list/', ReviewManagementView.as_view(), name='review_list'),
    path('review/delete/<int:id>/', delete_review, name='delete_review'),
    path('review-settings/', ReviewSettingsView.as_view(), name='review_settings'),

    #----------------- SoldCount ---------------------
    path('settings/sold-count/', SoldCountSettingsView.as_view(), name='sold_count_settings'),
    path('get-product-sold-count/<int:id>/', get_product_sold_count, name='get_product_sold_count'),

    # ------------------Order Request------------------
    path("order-requests/add/",AddOrderRequestView.as_view(),name="add_order_request"),
    path("order-requests/<int:pk>/edit/", AddOrderRequestView.as_view(), name="edit_order_request"),
    path("order-request/",OrderRequestListView.as_view(),name="order_request_list",),
    path("order-request/<int:id>/",OrderRequestDetailView.as_view(),name="order_request_detail",),
    path("order-request/<int:pk>/approve/",ApproveOrderRequestView.as_view(),name="approve_order_request",),
    path("order-request/<int:pk>/reject/",RejectOrderRequestView.as_view(),name="reject_order_request",),
    path("order-request/<int:pk>/work-status/", UpdateOrderRequestWorkStatusView.as_view(), name="update_order_request_work_status"),
    path('order-request/<int:pk>/update-status/', OrderRequestStatusUpdateView.as_view(), name='order_request_status_update'),
    
    path('settings/telegram-bot/', TelegramBotSettingsView.as_view(), name='telegram_bot_settings'),
    path('settings/telegram-bot/delete/<int:id>/', delete_telegram_bot_config, name='delete_telegram_bot_config'),
    path('settings/telegram-bot/toggle/<int:id>/', toggle_telegram_bot_active, name='toggle_telegram_bot_active'),

    # ------------------Attribute & Attribute Value------------------
    path('attribute-list/', AttributeView.as_view(), name='attribute_list'),
    path('attribute-value/<int:attribute_id>/', AttributeValueView.as_view(), name='attribute_value_list'),
    path('delete-attribute/<int:id>/', delete_attribute, name='delete_attribute'),
    path('delete-attribute-value/<int:id>/', delete_attribute_value, name='delete_attribute_value'),

    # ----------------- Slider ---------------------
    path('slider-list/', SliderView.as_view(), name='slider_list'),
    path('get-slider/<int:id>/', get_slider, name='get_slider'),
    path('delete-slider/<int:id>/', delete_slider, name='delete_slider'),
    path('toggle-slider/<int:id>/', toggle_slider_active, name='toggle_slider_active'),

    # ----------------- Pixel ---------------------
    path('settings/pixel/', PixelSettingsView.as_view(), name='pixel_settings'),

    # ----------------- Site Settings: Footer Links ---------------------
    path('settings/footer-links/', FooterLinkManagementView.as_view(), name='footer_links'),
    path('settings/footer-links/delete/<int:id>/', delete_footer_link, name='delete_footer_link'),
    path('settings/footer-links/toggle/<int:id>/', toggle_footer_link_active, name='toggle_footer_link_active'),

    # ----------------- Site Settings: Social Links ---------------------
    path('settings/social-links/', SocialLinkManagementView.as_view(), name='social_links'),
    path('settings/social-links/delete/<int:id>/', delete_social_link, name='delete_social_link'),
    path('settings/social-links/toggle/<int:id>/', toggle_social_link_active, name='toggle_social_link_active'),

    # ----------------- Site Settings: Navbar / Subnav Menu ---------------------
    path('settings/nav-menu/', NavMenuManagementView.as_view(), name='nav_menu'),
    path('settings/nav-menu/delete/<int:id>/', delete_nav_menu_link, name='delete_nav_menu_link'),
    path('settings/nav-menu/toggle/<int:id>/', toggle_nav_menu_link_active, name='toggle_nav_menu_link_active'),

    # ----------------- Site Settings: News Feed (Top Bar Ticker) ---------------------
    path('settings/news-feed/', NewsFeedManagementView.as_view(), name='news_feed'),
    path('settings/news-feed/delete/<int:id>/', delete_news_feed, name='delete_news_feed'),
    path('settings/news-feed/toggle/<int:id>/', toggle_news_feed_active, name='toggle_news_feed_active'),

    # ----------------- Todo -----------------
    path('todo-list/', TodoListView.as_view(), name='todo_list'),
    path('todo/add/', TodoCreateUpdateView.as_view(), name='todo_add'),
    path('todo/<int:pk>/edit/', TodoCreateUpdateView.as_view(), name='todo_edit'),
    path('todo/<int:pk>/toggle/', TodoToggleCompleteView.as_view(), name='todo_toggle'),
    path('todo/<int:pk>/delete/', TodoDeleteView.as_view(), name='todo_delete'),

    # ----------------- Reminder -----------------
    path('reminder-list/', ReminderListView.as_view(), name='reminder_list'),
    path('reminder/add/', ReminderCreateView.as_view(), name='reminder_add'),
    path('reminder/<int:pk>/toggle/', ReminderToggleCompleteView.as_view(), name='reminder_toggle'),
    path('reminder/<int:pk>/delete/', ReminderDeleteView.as_view(), name='reminder_delete'),

    # ----------------- Finance -----------------
    path('finance/maintenance-cost/', MaintenanceCostListView.as_view(), name='maintenance_cost_list'),
    path('finance/maintenance-cost/add/', MaintenanceCostCreateUpdateView.as_view(), name='maintenance_cost_add'),
    path('finance/maintenance-cost/<int:pk>/edit/', MaintenanceCostCreateUpdateView.as_view(), name='maintenance_cost_edit'),
    path('finance/maintenance-cost/<int:pk>/delete/', MaintenanceCostDeleteView.as_view(), name='maintenance_cost_delete'),
    path('finance/daily-profit/', DailyProfitListView.as_view(), name='daily_profit_list'),

    # ----------------- Invoice Color -----------------
    path('settings/invoice-color/', InvoiceColorSettingsView.as_view(), name='invoice_color_settings'),

    # ----------------- Today Work List (overview) -----------------
    path('today-work-list/', TodayWorkListView.as_view(), name='today_work_list'),

    # ----------------- Token -----------------
    path('orders/<int:pk>/token-print/', OrderTokenPrintView.as_view(), name='order_token_print'),
    path('orders/bulk-token-print/', OrderBulkTokenPrintView.as_view(), name='order_bulk_token_print'),

    path('orders/<int:pk>/pathao-submit/', OrderPathaoParcelSubmitView.as_view(), name='order_pathao_submit'),

    path('orders/<int:pk>/toggle-urgent/', OrderUrgentToggleView.as_view(), name='order_toggle_urgent'),
    path("stock-alert-list/", StockAlertListView.as_view(), name="stock_alert_list"),
    
    # ------------------ Marketing-----------
    path('marketing/utm-link-generator/', UTMLinkGeneratorView.as_view(), name='utm_link_generator'),
    path('marketing/traffic-source-report/', TrafficSourceReportView.as_view(), name='traffic_source_report'),

    #------------------ Coppon ---------
    path('settings/coupon/', CouponSettingsView.as_view(), name='coupon_settings'),
    path('settings/coupon/delete/<int:id>/', delete_coupon, name='delete_coupon'),
    path('settings/coupon/toggle/<int:id>/', toggle_coupon_active, name='toggle_coupon_active'),
    path('settings/coupon/<int:id>/usage/', coupon_usage_log, name='coupon_usage_log'),
    
]


router = DefaultRouter()
router.register("api/v1/attribute", AttributeAPIViews, basename="attribute"),
router.register("api/v1/tag", TagAPIViews, basename="tag")

urlpatterns += router.urls
