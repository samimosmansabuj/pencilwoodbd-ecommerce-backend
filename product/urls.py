from django.urls import path
from .api_views import CategoryAPIViews, CradleProductViews
from .api_views2 import TissueBoxLandingProductViews, TissueBoxLandingOrderAPI

app_name = "api"

urlpatterns = [
    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", CradleProductViews.as_view(), name="product_api"),

    # Tissue Box Landing Page
    path("api2/landing/tissue-box/products/", TissueBoxLandingProductViews.as_view(), name="tissue-box-products-2"),
    path("api2/landing/tissue-box/order/", TissueBoxLandingOrderAPI.as_view(), name="tissue-box-order-2"),
]
