from django.urls import path, include
from .api_views import CategoryAPIViews, CradleProductViews, LandingPageProductViews, LandingPageOrderAPI, GlobalCategoryViewSet, GlobalProductViewSet, GlobalOrderCreateApi, SendOTPAPIView, VerifyOTPAPIView, UnifiedLandingProductAPIView, UnifiedLandingOrderAPIView, CategoryListAPIView, ProductListAPIView, ProductDetailAPIView
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

    path('api/send-otp/', SendOTPAPIView.as_view()),
    path('api/verify-otp/', VerifyOTPAPIView.as_view()),

    path('products/', UnifiedLandingProductAPIView.as_view()),
    path('order/', UnifiedLandingOrderAPIView.as_view()),

    # ================= CATEGORY =================
    path('api/ecom/categories/', CategoryListAPIView.as_view(), name='category_list'),

    # ================= PRODUCTS =================
    path('api/ecom/products/', ProductListAPIView.as_view(), name='product_list'),
    path('api/ecom/products/<slug:slug>/', ProductDetailAPIView.as_view(), name='product_detail'),

]

