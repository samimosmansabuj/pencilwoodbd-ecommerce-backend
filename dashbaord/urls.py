from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import DashboardView, TodayWorkListView
from .api_views import AttributeAPIViews, TagAPIViews

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('today-work-list/', TodayWorkListView.as_view(), name='today_work_list'),
]

router = DefaultRouter()
router.register("api/v1/attribute", AttributeAPIViews, basename="attribute")
router.register("api/v1/tag", TagAPIViews, basename="tag")

urlpatterns += router.urls