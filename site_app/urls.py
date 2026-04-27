from django.urls import path
from .api_views import (
    HomePageAPIView,
)

urlpatterns = [
    path('api/home/', HomePageAPIView.as_view(), name='home_api'),
    
]