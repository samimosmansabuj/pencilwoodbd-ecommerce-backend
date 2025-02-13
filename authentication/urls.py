from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenVerifyView, TokenRefreshView
from .views import UserCreationViews, ProtectedView, UserListViews

urlpatterns = [
    path('auth/user-creation/', UserCreationViews.as_view(), name='user-creation'),
    path('auth/login/', TokenObtainPairView.as_view(), name='auth-login'),
    path('auth/token-verify/', TokenVerifyView.as_view(), name='token-verify'),
    path('auth/token-refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    path('auth/protect/', ProtectedView.as_view(), name='protect'),
    path('auth/user-list/', UserListViews.as_view(), name='user-list'),
]