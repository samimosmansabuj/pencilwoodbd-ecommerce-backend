from django.urls import path
from .api_views import CategoryAPIViews, CradleProductViews, LandingPageProductViews, LandingPageOrderAPI

app_name = "api"

urlpatterns = [
    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", CradleProductViews.as_view(), name="product_api"),
    
    path("api/product-fetch/<int:code>/", LandingPageProductViews.as_view(), name="product_fetch_api"),
    path("api/landing-page/order/create/", LandingPageOrderAPI.as_view(), name="order-create-api"),
]
