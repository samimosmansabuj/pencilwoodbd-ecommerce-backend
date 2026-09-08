from django.urls import path
from .views import (
    ProductListView, add_product, product_update, ProductDeleteView, ProductDuplicateView,
    CategoryView, get_category, delete_category,
    ProductFeatureView, delete_product_feature,
    FAQManagementView, delete_faq,
    ReviewManagementView, delete_review, ReviewSettingsView,
    SoldCountSettingsView, get_product_sold_count,
    AttributeView, delete_attribute, AttributeValueView, delete_attribute_value,
    StockAlertListView,
)

urlpatterns = [
    path('product-list/', ProductListView.as_view(), name='product_list'),
    path('product-add/', add_product, name='product_add'),
    path("product/update/<int:pk>/", product_update, name="product_update"),
    path('products/delete/<int:pk>/', ProductDeleteView.as_view(), name='product_delete'),
    path('products/duplicate/<int:pk>/', ProductDuplicateView.as_view(), name='product_duplicate'),

    path('category-list/', CategoryView.as_view(), name='category_list'),
    path('get-category/<int:id>/', get_category, name='get_category'),
    path('delete-category/<int:id>/', delete_category, name='delete_category'),

    # ----------------- Product Features ---------------------
    path('product/<int:product_id>/features/', ProductFeatureView.as_view(), name='product_features'),
    path('product-feature/delete/<int:id>/', delete_product_feature, name='delete_product_feature'),

    # ----------------- FAQ ---------------------
    path('faq-list/', FAQManagementView.as_view(), name='faq_list'),
    path('faq/delete/<int:id>/', delete_faq, name='delete_faq'),

    # ----------------- Reviews ---------------------
    path('review-list/', ReviewManagementView.as_view(), name='review_list'),
    path('review/delete/<int:id>/', delete_review, name='delete_review'),
    path('review-settings/', ReviewSettingsView.as_view(), name='review_settings'),

    # ----------------- SoldCount ---------------------
    path('settings/sold-count/', SoldCountSettingsView.as_view(), name='sold_count_settings'),
    path('get-product-sold-count/<int:id>/', get_product_sold_count, name='get_product_sold_count'),

    # ----------------- Attribute & Attribute Value ------------------
    path('attribute-list/', AttributeView.as_view(), name='attribute_list'),
    path('attribute-value/<int:attribute_id>/', AttributeValueView.as_view(), name='attribute_value_list'),
    path('delete-attribute/<int:id>/', delete_attribute, name='delete_attribute'),
    path('delete-attribute-value/<int:id>/', delete_attribute_value, name='delete_attribute_value'),

    # ----------------- Stock Alert ---------------------
    path("stock-alert-list/", StockAlertListView.as_view(), name="stock_alert_list"),
]

