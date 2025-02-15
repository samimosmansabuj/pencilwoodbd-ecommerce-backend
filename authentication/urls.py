from django.urls import path
from rest_framework_simplejwt.views import TokenVerifyView, TokenRefreshView
from .views import AdminCreationViews, ProtectedView, UserListViews, CustomerRegistrationViews, CustomerTokenObtainPairViews, AdminTokenObtainPairViews

urlpatterns = [
    #Admin User Authentication & Creation
    path('auth/user-creation/', AdminCreationViews.as_view(), name='user-creation'),
    path('auth/admin-login/', AdminTokenObtainPairViews.as_view(), name='admin-login'),
    
    #Customer User Authentication & Registraion
    path('auth/registration/', CustomerRegistrationViews.as_view(), name='customer-registration'),
    path('auth/login/', CustomerTokenObtainPairViews.as_view(), name='login'),
    
    #Token Refresh & Verify
    path('auth/token-verify/', TokenVerifyView.as_view(), name='token-verify'),
    path('auth/token-refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    #User List & Protect Testing
    path('auth/protect/', ProtectedView.as_view(), name='protect'),
    path('auth/user-list/', UserListViews.as_view(), name='user-list'),
]