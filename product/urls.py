from django.urls import path
from .api_views import CategoryAPIViews, ProductViews
from .api_views2 import *
app_name = "api"


urlpatterns = [
    
    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", ProductViews.as_view(), name="product_api"),
# for tissue-box-landing page
    path("api2/categories/", CategoryAPIViews2.as_view(), name="categories-api-2"),
    path("api2/landing/tissue-box/products/",TissueBoxLandingProductViews.as_view(),name="tissue-box-products-2"),
    path("api2/landing/tissue-box/order/",TissueBoxLandingOrderAPI.as_view(),name="tissue-box-order-2"),
]