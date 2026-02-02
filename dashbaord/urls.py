from django.urls import path, include
from .views import *

urlpatterns = [
    path('', dashboard, name='dashboard'),
    
    path('admin-login/', UserLoginView.as_view(), name='admin_login'),
    path('admin-logout/', logout_view, name='admin_logout'),
    
    path('product-list/', product_list, name='product_list'),
    path('product-add/', add_product, name='product_add'),
    # path('media-center/', product_list, name='media_center'),

    path('category-list/', CategoryView.as_view(), name='category_list'),
    path('category-add/', add_category, name='category_add'),
    path('get-category/<int:id>/', get_category, name='get_category'),
    path('delete-category/<int:id>/', delete_category, name='delete_category'),

    path('order-list/', OrderView.as_view(), name='order_list'),
    path('order-detail/<int:id>/', OrderDetailView.as_view(), name='order_detail'),

#     path('dashboard/product/list/', ProductListView.as_view(), name='product_list'),
#     path('dashboard/product/add/', ProductCreateView.as_view(), name='add_product'),
#     path('dashboard/product/update/<int:pk>/', ProductUpdateView.as_view(), name='update_product'),
#     path('dashboard/product/delete/<int:pk>/', ProductDeleteView.as_view(), name='delete_product'),
    
#     path('dashboard/category/list/', CategoryListView.as_view(), name='category_list'),
#     path('dashboard/category/add/', CategoryCreateView.as_view(), name='add_category'),
#     path('dashboard/category/update/<int:pk>/', CategoryUpdateView.as_view(), name='update_category'),
#     path('dashboard/category/delete/<int:pk>/', CategoryDeleteView.as_view(), name='delete_category'),
    
#     path('dashboard/order/list/', OrdertListView.as_view(), name='order_list'),
#     # path('order/add/', OrderCreateView.as_view(), name='add_order'),
#     path('dashboard/order/update/<int:pk>/', OrderUpdateView.as_view(), name='update_order'),
#     path('dashboard/order/delete/<int:pk>/', OrderDeleteView.as_view(), name='delete_order'),
]
