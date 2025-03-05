from rest_framework import serializers
from .models import Category, Product, AddToCart, FreeAddToCart, ProductImage

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image']
        read_only_fields = ['id']

class ProductSerializer(serializers.ModelSerializer):
    product_image = ProductImageSerializer(many=True, required=False)
    class Meta:
        model = Product
        fields = [
            'id', 'category', 'name', 'slug', 'short_description', 'details', 
            'variation', 'current_price', 'discount_price', 'created_at', 'updated_at', 'product_image'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        images_data = self.context['request'].FILES.getlist('product_image')
        product = Product.objects.create(**validated_data)
        for image in images_data:
            ProductImage.objects.create(product=product, image=image)
        return product
    
    def update(self, instance, validated_data):
        images_data = self.context['request'].FILES.getlist('product_image')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        for image in images_data:
            ProductImage.objects.create(product=instance, image=image)
        return instance


class AddToCartSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=True)
    class Meta:
        model = AddToCart
        fields = '__all__'
        read_only_fields = ('price', 'discount_price', 'total_price')


class FreeAddToCartSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreeAddToCart
        fields = '__all__'
