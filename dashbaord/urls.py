from django.urls import path, include
from .views import *
from .api_views import *
from rest_framework.routers import DefaultRouter

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    
    path('admin-login/', UserLoginView.as_view(), name='admin_login'),
    path('admin-logout/', AdminLogoutView.as_view(), name='admin_logout'),
    

    path('users/', UserManagementView.as_view(), name='user_management'),
    path("users/staff/create/", StaffCreateView.as_view(), name="staff_create"),
    path("users/staff/<int:pk>/edit/", StaffUpdateView.as_view(), name="staff_update"),

    path('product-list/', ProductListView.as_view(), name='product_list'),
    path('product-add/', add_product, name='product_add'),
    path("product/update/<int:pk>/", product_update, name="product_update"),
    path('products/delete/<int:pk>/', ProductDeleteView.as_view(), name='product_delete'),  


    # path('media-center/', product_list, name='media_center'),

    path('category-list/', CategoryView.as_view(), name='category_list'),
    # path('category-add/', add_category, name='category_add'),
    path('get-category/<int:id>/', get_category, name='get_category'),
    path('delete-category/<int:id>/', delete_category, name='delete_category'),

    path("orders/add/",AddOrderView.as_view(),name="add_order"),
    path('order-list/', OrderView.as_view(), name='order_list'),
    path('order-detail/<int:id>/', OrderDetailView.as_view(), name='order_detail'),
    path('order-detail/<int:pk>/update/', OrderUpdateView.as_view(), name='order_update_full'),
    path('orders/delete/<int:pk>/', OrderDeleteView.as_view(), name='order_delete'),
    path('orders/delivery-option-submit/<int:pk>/', OrderDeliveryOptionSubmitView.as_view(), name='order_delivery_option_submit'),
    path('orders/<int:id>/invoice/', OrderInvoiceView.as_view(), name='order_invoice'),
    path('order-detail/<int:order_id>/update/', update_order, name='order_update'),

    # ------------------Order Request------------------
    path("order-requests/add/",AddOrderRequestView.as_view(),name="add_order_request"),
    path("order-requests/<int:pk>/edit/", AddOrderRequestView.as_view(), name="edit_order_request"),
    path("order-request/",OrderRequestListView.as_view(),name="order_request_list",),
    path("order-request/<int:id>/",OrderRequestDetailView.as_view(),name="order_request_detail",),
    path("order-request/<int:pk>/approve/",ApproveOrderRequestView.as_view(),name="approve_order_request",),
    path("order-request/<int:pk>/reject/",RejectOrderRequestView.as_view(),name="reject_order_request",),
    path("order-request/<int:pk>/work-status/", UpdateOrderRequestWorkStatusView.as_view(), name="update_order_request_work_status"),

    # ------------------Attribute & Attribute Value------------------
    path('attribute-list/', AttributeView.as_view(), name='attribute_list'),
    path('attribute-value/<int:attribute_id>/', AttributeValueView.as_view(), name='attribute_value_list'),
    path('delete-attribute/<int:id>/', delete_attribute, name='delete_attribute'),
    path('delete-attribute-value/<int:id>/', delete_attribute_value, name='delete_attribute_value'),

]


router = DefaultRouter()
router.register("api/v1/attribute", AttributeAPIViews, basename="attribute"),
router.register("api/v1/tag", TagAPIViews, basename="tag")

urlpatterns += router.urls
