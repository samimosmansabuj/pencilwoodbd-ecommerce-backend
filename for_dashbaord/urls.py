from django.urls import path, include
from .views import *

urlpatterns = [
    path('', index, name='index'),
    
    path('product/list/', ProductListView.as_view(), name='product_list'),
    path('product/add/', ProductCreateView.as_view(), name='add_product'),
    path('product/update/<int:pk>/', ProductUpdateView.as_view(), name='update_product'),
    path('product/delete/<int:pk>/', ProductDeleteView.as_view(), name='delete_product'),
    
    path('category/list/', CategoryListView.as_view(), name='category_list'),
    path('category/add/', CategoryCreateView.as_view(), name='add_category'),
    path('category/update/<int:pk>/', CategoryUpdateView.as_view(), name='update_category'),
    path('category/delete/<int:pk>/', CategoryDeleteView.as_view(), name='delete_category'),
    
    path('order/list/', OrdertListView.as_view(), name='order_list'),
    # path('order/add/', OrderCreateView.as_view(), name='add_order'),
    path('order/update/<int:pk>/', OrderUpdateView.as_view(), name='update_order'),
    path('order/delete/<int:pk>/', OrderDeleteView.as_view(), name='delete_order'),
    
    path('login/', login, name='login')
]