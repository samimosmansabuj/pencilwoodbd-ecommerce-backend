from django.urls import path
from .api_views import (
    HomePageAPIView,
    LandingPageAPIView,
)

urlpatterns = [
    path('api/home/', HomePageAPIView.as_view(), name='home_api'),
    path('api/landing/', LandingPageAPIView.as_view(), name="landing_page"),
]