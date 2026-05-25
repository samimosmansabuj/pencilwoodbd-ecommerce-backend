from django.urls import path
from .api_views import (
    AuthRegisterAPIView,
    AuthLoginAPIView,
    UserProfileAPIView,
    LogoutAPIView,
    
)

urlpatterns = [
    # ================= AUTH =================
    path('api/auth/register/', AuthRegisterAPIView.as_view(), name='auth_register'),
    path('api/auth/login/', AuthLoginAPIView.as_view(), name='auth_login'),

    # ================= PROFILE =================
    path('api/auth/profile/', UserProfileAPIView.as_view(), name='user_profile'),

    path('api/auth/logout/', LogoutAPIView.as_view(), name='auth_logout'),
]