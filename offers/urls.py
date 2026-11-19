from django.urls import path

from .api_views import ProductOffersAPIView
from .views import (
    OfferListView,
    OfferDataView,
    OfferSaveView,
    OfferToggleView,
    OfferDeleteView,
    ComboAddView,
    ComboDeleteView,
)

urlpatterns = [
    # API
    path("api/offers/product/<int:product_id>/", ProductOffersAPIView.as_view(), name="offers_for_product"),

    # dashboard
    path("settings/offers/", OfferListView.as_view(), name="offer_settings"),
    path("settings/offers/<int:pk>/data/", OfferDataView.as_view(), name="offer_data"),
    path("settings/offers/save/", OfferSaveView.as_view(), name="offer_save"),
    path("settings/offers/<int:pk>/toggle/", OfferToggleView.as_view(), name="offer_toggle"),
    path("settings/offers/<int:pk>/delete/", OfferDeleteView.as_view(), name="offer_delete"),
    path("settings/offers/combos/add/", ComboAddView.as_view(), name="offer_combo_add"),
    path("settings/offers/combos/<int:pk>/delete/", ComboDeleteView.as_view(), name="offer_combo_delete"),
]
