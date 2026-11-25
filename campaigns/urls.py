from django.urls import path

from .api_views import CampaignDetailAPIView, CampaignListAPIView
from .views import (
    CampaignDeleteView,
    CampaignDuplicateView,
    CampaignFormView,
    CampaignListView,
    CampaignSaveView,
    CampaignToggleView,
    PopupDataView,
    PopupDeleteView,
    PopupListView,
    PopupSaveView,
    PopupToggleView,
    ProductSearchView,
)

urlpatterns = [
    path("api/ecom/campaigns/", CampaignListAPIView.as_view(), name="campaign_list"),
    path("api/ecom/campaigns/<slug:slug>/", CampaignDetailAPIView.as_view(), name="campaign_detail"),
]

urlpatterns += [
    path("campaigns/", CampaignListView.as_view(), name="campaign_list"),
    path("campaigns/new/", CampaignFormView.as_view(), name="campaign_add"),
    path("campaigns/save/", CampaignSaveView.as_view(), name="campaign_save"),
    path("campaigns/product-search/", ProductSearchView.as_view(), name="campaign_product_search"),
    path("campaigns/<int:pk>/edit/", CampaignFormView.as_view(), name="campaign_edit"),
    path("campaigns/<int:pk>/toggle/", CampaignToggleView.as_view(), name="campaign_toggle"),
    path("campaigns/<int:pk>/duplicate/", CampaignDuplicateView.as_view(), name="campaign_duplicate"),
    path("campaigns/<int:pk>/delete/", CampaignDeleteView.as_view(), name="campaign_delete"),

    path("popups/", PopupListView.as_view(), name="popup_list"),
    path("popups/save/", PopupSaveView.as_view(), name="popup_save"),
    path("popups/<int:pk>/data/", PopupDataView.as_view(), name="popup_data"),
    path("popups/<int:pk>/toggle/", PopupToggleView.as_view(), name="popup_toggle"),
    path("popups/<int:pk>/delete/", PopupDeleteView.as_view(), name="popup_delete"),
]
