from django.urls import path, include
from .views import *

urlpatterns = [
    path('', index, name='index'),
    path('product/list/', product_list, name='product_list'),
]