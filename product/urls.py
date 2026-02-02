from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewset, ProductViewset
from .api_views import CategoryAPIViews, ProductViews

app_name = "api"

router = DefaultRouter()
router.register(r'category', CategoryViewset, basename='category')
router.register(r'product', ProductViewset, basename='product')
# router.register(r'cart', AddToCartViewset, basename='cart')


urlpatterns = [
    path('', include(router.urls)),

    path("api/category/", CategoryAPIViews.as_view(), name="category_api"),
    path("api/product/", ProductViews.as_view(), name="product_api"),
]