from rest_framework import serializers
from .models import Category, Product, AddToCart, FreeAddToCart

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class AddToCartSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=True)
    class Meta:
        model = AddToCart
        fields = '__all__'


class FreeAddToCartSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreeAddToCart
        fields = '__all__'
