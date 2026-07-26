from django.urls import path
from .api_views import (
    PhoneCheckAPIView,
    SetPasswordAPIView,
    PhoneLoginAPIView,
    UserProfileAPIView,
    LogoutAPIView,
)

urlpatterns = [
    path('api/auth/phone-check/', PhoneCheckAPIView.as_view(), name='auth_phone_check'),
    path('api/auth/set-password/', SetPasswordAPIView.as_view(), name='auth_set_password'),
    path('api/auth/phone-login/', PhoneLoginAPIView.as_view(), name='auth_phone_login'),

    path('api/auth/profile/', UserProfileAPIView.as_view(), name='user_profile'),
    path('api/auth/logout/', LogoutAPIView.as_view(), name='auth_logout'),
]