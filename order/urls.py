from django.urls import path
from .api_views import OrderCreateAPIView

urlpatterns = [
    
    
    
    
    
    path('api/create-order/', OrderCreateAPIView.as_view(), name="create-order")
]