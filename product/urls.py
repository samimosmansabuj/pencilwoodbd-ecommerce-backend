from django.urls import path, include
from .api_views import CategoryAPIViews, CradleProductViews, LandingPageProductViews, LandingPageOrderAPI, GlobalCategoryViewSet, GlobalProductViewSet, GlobalOrderCreateApi
from rest_framework.routers import DefaultRouter

global_api_router = DefaultRouter()
global_api_router.register(r"categories", GlobalCategoryViewSet, basename="global-category")
global_api_router.register(r"products", GlobalProductViewSet, basename="global-product")

app_name = "api"

urlpatterns = [
    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", CradleProductViews.as_view(), name="product_api"),
    
    path("api/product-fetch/<int:code>/", LandingPageProductViews.as_view(), name="product_fetch_api"),
    path("api/landing-page/order/create/", LandingPageOrderAPI.as_view(), name="order-create-api"),
    
    
    path("api/", include(global_api_router.urls)),
    path("api/order/create/", GlobalOrderCreateApi.as_view(),name="global-order-create" ),
]

