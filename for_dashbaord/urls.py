from django.urls import path, include
from .views import *

urlpatterns = [
    path('', index, name='index'),
    
    path('login/', AdminLoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    
    path('dashboard/product/list/', ProductListView.as_view(), name='product_list'),
    path('dashboard/product/add/', ProductCreateView.as_view(), name='add_product'),
    path('dashboard/product/update/<int:pk>/', ProductUpdateView.as_view(), name='update_product'),
    path('dashboard/product/delete/<int:pk>/', ProductDeleteView.as_view(), name='delete_product'),
    
    path('dashboard/category/list/', CategoryListView.as_view(), name='category_list'),
    path('dashboard/category/add/', CategoryCreateView.as_view(), name='add_category'),
    path('dashboard/category/update/<int:pk>/', CategoryUpdateView.as_view(), name='update_category'),
    path('dashboard/category/delete/<int:pk>/', CategoryDeleteView.as_view(), name='delete_category'),
    
    path('dashboard/order/list/', OrdertListView.as_view(), name='order_list'),
    # path('order/add/', OrderCreateView.as_view(), name='add_order'),
    path('dashboard/order/update/<int:pk>/', OrderUpdateView.as_view(), name='update_order'),
    path('dashboard/order/delete/<int:pk>/', OrderDeleteView.as_view(), name='delete_order'),
]