from django.urls import path
from .api_views import (
    HomePageAPIView,
    LandingPageProductViews,
    LandingPageOrderAPI,
    OrderCreateAPIView
)

urlpatterns = [
    path('api/home/', HomePageAPIView.as_view(), name='home_api'),
    path('api/landing-page/<int:code>/', LandingPageProductViews.as_view(), name="landing_page"),
    path("api/landing/order/", LandingPageOrderAPI.as_view()),
    
    path('api/create-order/', OrderCreateAPIView.as_view(), name="create-order"),
]