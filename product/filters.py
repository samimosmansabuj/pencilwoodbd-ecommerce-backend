import django_filters
from .models import Product

class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="current_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="current_price", lookup_expr="lte")
    category = django_filters.BaseInFilter(field_name="category_id", lookup_expr="in")
    
    class Meta:
        model = Product
        fields = ["category", "min_price", "max_price"]