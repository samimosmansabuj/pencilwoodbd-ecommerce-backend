from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewset, ProductViewset, AddToCartViewset, FreeAddToCartViewset

router = DefaultRouter()
router.register(r'category', CategoryViewset, basename='category')
router.register(r'product', ProductViewset, basename='product')
router.register(r'cart', AddToCartViewset, basename='cart')
router.register(r'free-cart', FreeAddToCartViewset, basename='free-cart')


urlpatterns = [
    path('', include(router.urls)),
]