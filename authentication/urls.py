from django.urls import path
from .api_views import (
    PhoneCheckAPIView,
    SetPasswordAPIView,
    PhoneLoginAPIView,
    ResetPasswordAPIView,      
    UserProfileAPIView,
    LogoutAPIView,
    GoogleLoginAPIView,
)
from .views import *

urlpatterns = [
    path('api/auth/phone-check/', PhoneCheckAPIView.as_view(), name='auth_phone_check'),
    path('api/auth/set-password/', SetPasswordAPIView.as_view(), name='auth_set_password'),
    path('api/auth/phone-login/', PhoneLoginAPIView.as_view(), name='auth_phone_login'),
    path('api/auth/reset-password/', ResetPasswordAPIView.as_view(), name='auth_reset_password'),
    path('api/auth/google-login/', GoogleLoginAPIView.as_view(), name='auth_google_login'),
    
    path('api/auth/profile/', UserProfileAPIView.as_view(), name='user_profile'),
    path('api/auth/logout/', LogoutAPIView.as_view(), name='auth_logout'),

    path('landing-pages/', LandingPageListView.as_view(), name='landing_page_list'),
    path('landing-pages/add/', LandingPageAddView.as_view(), name='landing_page_add'),
    path('landing-pages/<int:pk>/edit/', LandingPageEditView.as_view(), name='landing_page_edit'),
    path('landing-pages/<int:pk>/delete/', LandingPageDeleteView.as_view(), name='landing_page_delete'),

        #------------------ IP/Device Security -----------
    path('security/blocked-list/', BlockedIdentityListView.as_view(), name='blocked_identity_list'),
    path('security/blocked-list/order-mode/', BlockedOrderModeUpdateView.as_view(), name='blocked_order_mode_update'),
    path('security/courier-check/', CourierCheckSettingsView.as_view(), name='courier_check_settings'),
    path('security/courier-check/badge/', CourierBadgeCheckView.as_view(), name='courier_badge_check'),
    path('security/courier-check/history/', CourierCheckHistoryView.as_view(), name='courier_check_history'),
    path('security/courier-check/number-retention/', CourierNumberRetentionView.as_view(), name='courier_number_retention'),
    path('security/courier-check/cleanup/', CourierCheckCleanupView.as_view(), name='courier_check_cleanup'),
    path('security/courier-check/restricted/clear/', CourierRestrictedClearView.as_view(), name='courier_restricted_clear'),
    path('security/blocked-list/<int:pk>/unblock/', UnblockIdentityView.as_view(), name='unblock_identity'),
    path('order/<str:order_id>/block-identity/', BlockOrderIdentityView.as_view(), name='block_order_identity'),
    path('order/<str:order_id>/unblock-identity/', UnblockOrderIdentityView.as_view(), name='unblock_order_identity'),

    # ----------------- Dashboard: Auth / Staff Management -----------------
    path('admin-login/', UserLoginView.as_view(), name='admin_login'),
    path('admin-logout/', AdminLogoutView.as_view(), name='admin_logout'),

    path('users/', UserManagementView.as_view(), name='user_management'),
    path("users/staff/create/", StaffCreateView.as_view(), name="staff_create"),
    path("users/staff/<int:pk>/edit/", StaffUpdateView.as_view(), name="staff_update"),
]