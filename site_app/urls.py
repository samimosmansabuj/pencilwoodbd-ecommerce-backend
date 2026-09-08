from django.urls import path
from .api_views import (
    HomePageAPIView,
    LandingPageProductViews,
    LandingPageOrderAPI,
    OrderCreateAPIView,
    ApplyCouponAPIView
)
from .views import *


urlpatterns = [
    path('api/home/', HomePageAPIView.as_view(), name='home_api'),
    path('api/landing-page/<int:code>/', LandingPageProductViews.as_view(), name="landing_page"),
    path("api/landing/order/", LandingPageOrderAPI.as_view()),
    
    path('api/create-order/', OrderCreateAPIView.as_view(), name="create-order"),

    path("api/apply-coupon/", ApplyCouponAPIView.as_view(), name="apply-coupon"),

    # ----------------- Showcase Media ---------------------
    path('showcase-list/', ShowcaseMediaView.as_view(), name='showcase_list'),
    path('get-showcase/<int:id>/', get_showcase_item, name='get_showcase_item'),
    path('delete-showcase/<int:id>/', delete_showcase_item, name='delete_showcase_item'),
    path('toggle-showcase/<int:id>/', toggle_showcase_active, name='toggle_showcase_active'),

    # ----------------- Home Sections (master on/off switches) ---------------------
    path('home-sections/', HomeSectionManagementView.as_view(), name='home_section_list'),
    path('home-sections/get/<int:id>/', get_home_section, name='get_home_section'),
    path('home-sections/delete/<int:id>/', delete_home_section, name='delete_home_section'),
    path('home-sections/toggle/<int:id>/', toggle_home_section_active, name='toggle_home_section_active'),

    # ----------------- Why Choose Us Cards ---------------------
    path('why-choose-us/', WhyChooseUsManagementView.as_view(), name='why_choose_list'),
    path('why-choose-us/get/<int:id>/', get_why_choose_item, name='get_why_choose_item'),
    path('why-choose-us/delete/<int:id>/', delete_why_choose_item, name='delete_why_choose_item'),
    path('why-choose-us/toggle/<int:id>/', toggle_why_choose_active, name='toggle_why_choose_active'),

    # ----------------- Slider ---------------------
    path('slider-list/', SliderView.as_view(), name='slider_list'),
    path('get-slider/<int:id>/', get_slider, name='get_slider'),
    path('delete-slider/<int:id>/', delete_slider, name='delete_slider'),
    path('toggle-slider/<int:id>/', toggle_slider_active, name='toggle_slider_active'),

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

    # ----------------- Delivery Charge (site-wide) -----------------
    path('settings/delivery-charge/', DeliveryChargeSettingsView.as_view(), name='delivery_charge_settings'),
]