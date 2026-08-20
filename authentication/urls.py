from django.urls import path
from .api_views import (
    PhoneCheckAPIView,
    SetPasswordAPIView,
    PhoneLoginAPIView,
    UserProfileAPIView,
    LogoutAPIView,
)
from .views import *

urlpatterns = [
    path('api/auth/phone-check/', PhoneCheckAPIView.as_view(), name='auth_phone_check'),
    path('api/auth/set-password/', SetPasswordAPIView.as_view(), name='auth_set_password'),
    path('api/auth/phone-login/', PhoneLoginAPIView.as_view(), name='auth_phone_login'),

    path('api/auth/profile/', UserProfileAPIView.as_view(), name='user_profile'),
    path('api/auth/logout/', LogoutAPIView.as_view(), name='auth_logout'),

    path('landing-pages/', LandingPageListView.as_view(), name='landing_page_list'),
    path('landing-pages/add/', LandingPageAddView.as_view(), name='landing_page_add'),
    path('landing-pages/<int:pk>/edit/', LandingPageEditView.as_view(), name='landing_page_edit'),
    path('landing-pages/<int:pk>/delete/', LandingPageDeleteView.as_view(), name='landing_page_delete'),
]