from django.urls import path
from .api_views import (
    HomePageAPIView,
    LandingPageProductViews,
    LandingPageOrderAPI,
    OrderCreateAPIView,
    ApplyCouponAPIView
)
from .views import *


urlpatterns = [
    path('api/home/', HomePageAPIView.as_view(), name='home_api'),
    path('api/landing-page/<int:code>/', LandingPageProductViews.as_view(), name="landing_page"),
    path("api/landing/order/", LandingPageOrderAPI.as_view()),
    
    path('api/create-order/', OrderCreateAPIView.as_view(), name="create-order"),

    path("api/apply-coupon/", ApplyCouponAPIView.as_view(), name="apply-coupon"),

    # ----------------- Showcase Media ---------------------
    path('showcase-list/', ShowcaseMediaView.as_view(), name='showcase_list'),
    path('get-showcase/<int:id>/', get_showcase_item, name='get_showcase_item'),
    path('delete-showcase/<int:id>/', delete_showcase_item, name='delete_showcase_item'),
    path('toggle-showcase/<int:id>/', toggle_showcase_active, name='toggle_showcase_active'),
]