from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.contrib import admin
from .views import (
    HomeSliderViewSet, NewsFeedViewSet, 
    SocialLinkViewSet, FooterTagLinkViewSet, AboutWhyChooseUsViewSet, 
    ContactInformationView, RefundPolicyView, TermsAndConditionView, 
    PrivacyPolicyView, FAQListViewSet, SiteContentView, SiteColorSectionView, AboutUsView
)


admin.site.site_header = "Pencilwood BD"
admin.site.site_title = "Pencilwood BD"
admin.site.index_title = "Welcome to Pencilwood BD"
# admin.site.index_template = "OK"

router = DefaultRouter()
router.register(r'home-slider', HomeSliderViewSet)
router.register(r'news-feed', NewsFeedViewSet)
router.register(r'social-link', SocialLinkViewSet)
router.register(r'footer-tag-link', FooterTagLinkViewSet)
router.register(r'about-why-choose-us', AboutWhyChooseUsViewSet)
router.register(r'faq-list', FAQListViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('site-content/', SiteContentView.as_view(), name='site-content'),
    path('site-color/', SiteColorSectionView.as_view(), name='site-color'),
    path('about-us/', AboutUsView.as_view(), name='about-us'),
    path('contact-information/', ContactInformationView.as_view(), name='contact-information'),
    path('refund-policy/', RefundPolicyView.as_view(), name='refund-policy'),
    path('terms-and-conditions/', TermsAndConditionView.as_view(), name='terms-and-conditions'),
    path('privacy-policy/', PrivacyPolicyView.as_view(), name='privacy-policy'),
]
