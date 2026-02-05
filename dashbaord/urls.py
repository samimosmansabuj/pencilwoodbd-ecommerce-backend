from django.urls import path, include
from .views import *

urlpatterns = [
    path('', dashboard, name='dashboard'),
    
    path('admin-login/', UserLoginView.as_view(), name='admin_login'),
    path('admin-logout/', logout_view, name='admin_logout'),
    
    path('product-list/', product_list, name='product_list'),
    path('product-add/', add_product, name='product_add'),
    path("product/update/<int:pk>/", product_update, name="product_update"),
    path('products/delete/<int:pk>/', product_delete, name='product_delete'),  


    # path('media-center/', product_list, name='media_center'),

    path('category-list/', CategoryView.as_view(), name='category_list'),
    path('category-add/', add_category, name='category_add'),
    path('get-category/<int:id>/', get_category, name='get_category'),
    path('delete-category/<int:id>/', delete_category, name='delete_category'),

    path('order-list/', OrderView.as_view(), name='order_list'),
    path('order-detail/<int:id>/', OrderDetailView.as_view(), name='order_detail'),
    path('orders/delete/<int:pk>/', OrderDeleteView.as_view(), name='order_delete'),
    path('order-detail/<int:order_id>/update/', update_order, name='order_update'),

]
