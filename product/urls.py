from django.urls import path
from .api_views import CategoryAPIViews, CradleProductViews, LandingPageProductViews, LandingPageOrderAPI, GlobalCategoryApi, GlobalProductApi, GlobalOrderCreateApi

app_name = "api"

urlpatterns = [
    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", CradleProductViews.as_view(), name="product_api"),
    
    path("api/product-fetch/<int:code>/", LandingPageProductViews.as_view(), name="product_fetch_api"),
    path("api/landing-page/order/create/", LandingPageOrderAPI.as_view(), name="order-create-api"),
    
    path("api/categories/",GlobalCategoryApi.as_view(),name="global-categories"),
    path("api/products/",GlobalProductApi.as_view(),name="global-products"),
    path("api/order/create/", GlobalOrderCreateApi.as_view(),name="global-order-create" ),
]
