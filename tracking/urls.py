from django.urls import path
from .api_views import TrackEventAPIView, IdentifyVisitorAPIView
from .views import CustomerActivityView, VisitorListView

urlpatterns = [
    # ----------------- Public tracking API -----------------
    path("api/tracking/event/", TrackEventAPIView.as_view(), name="track_event"),
    path("api/tracking/identify/", IdentifyVisitorAPIView.as_view(), name="track_identify"),

    # ----------------- Dashboard: activity viewing (staff only) -----------------
    path("visitors/", VisitorListView.as_view(), name="visitor_list"),
    path("customers/<int:pk>/activity/", CustomerActivityView.as_view(), name="customer_activity"),
]
