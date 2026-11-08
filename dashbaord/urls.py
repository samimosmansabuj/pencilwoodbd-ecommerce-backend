from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardView, TodayWorkListView, TodayOrderProductsView, PendingProductsView,
    SalesReportView, SalesReportExportView, SalesReportExcelView,
)
from .api_views import AttributeAPIViews, TagAPIViews

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('today-work-list/', TodayWorkListView.as_view(), name='today_work_list'),
    path('today-order-products/', TodayOrderProductsView.as_view(), name='today_order_products'),
    path('pending-products/', PendingProductsView.as_view(), name='pending_products'),
    path('reports/sales/', SalesReportView.as_view(), name='sales_report'),
    path('reports/sales/export/', SalesReportExportView.as_view(), name='sales_report_export'),
    path('reports/sales/export-xlsx/', SalesReportExcelView.as_view(), name='sales_report_export_xlsx'),
]

router = DefaultRouter()
router.register("api/v1/attribute", AttributeAPIViews, basename="attribute")
router.register("api/v1/tag", TagAPIViews, basename="tag")

urlpatterns += router.urls