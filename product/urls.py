from django.urls import path
from .api_views import CategoryAPIViews, ProductViews

app_name = "api"


urlpatterns = [
    
    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", ProductViews.as_view(), name="product_api"),
]