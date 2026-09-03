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

    # ----------------- Home Sections (master on/off switches) ---------------------
    path('home-sections/', HomeSectionManagementView.as_view(), name='home_section_list'),
    path('home-sections/get/<int:id>/', get_home_section, name='get_home_section'),
    path('home-sections/delete/<int:id>/', delete_home_section, name='delete_home_section'),
    path('home-sections/toggle/<int:id>/', toggle_home_section_active, name='toggle_home_section_active'),

    # ----------------- Why Choose Us Cards ---------------------
    path('why-choose-us/', WhyChooseUsManagementView.as_view(), name='why_choose_list'),
    path('why-choose-us/get/<int:id>/', get_why_choose_item, name='get_why_choose_item'),
    path('why-choose-us/delete/<int:id>/', delete_why_choose_item, name='delete_why_choose_item'),
    path('why-choose-us/toggle/<int:id>/', toggle_why_choose_active, name='toggle_why_choose_active'),
]