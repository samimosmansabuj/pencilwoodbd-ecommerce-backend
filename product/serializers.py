from rest_framework import serializers
from .models import Category, Product, ProductImage, ProductGifting, ProductDeliveryCharge, ProductVariant

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image']
        read_only_fields = ['id']

class ProductGiftingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductGifting
        fields = ["gift_type", "gift_product", "value"]
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        gift_product = Product.objects.get(pk=data.get("gift_product"))
        data["gift_product"] = {
            "id": gift_product.id,
            "name": gift_product.name,
            "discount_price": gift_product.discount_price,
        }
        return data

class ProductDeliveryChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductDeliveryCharge
        fields = ["area_and_charge"]



class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "price",
            "discount_price",
            "inventory_quantity",
            "attributes"
        ]

class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True)
    gift_product = ProductGiftingSerializer(many=True)
    delivery_charge = ProductDeliveryChargeSerializer()
    variants = ProductVariantSerializer(many=True, read_only=True)


    class Meta:
        model = Product
        fields = [
            'id', 'category', 'name', 'slug', 'short_description', 'details', 
            'inventory_quantity', 'price', 'discount_price', 'created_at', 'updated_at', 'images', 'gift_product', 'delivery_charge', 'variants'
        ]
        read_only_fields = ['id', 'slug', 'delivery_charge', 'gift_product', 'created_at', 'updated_at']
    
    
    def get_variants(self, obj):
        variants_qs = obj.variants.filter(is_active=True)  
        return ProductVariantSerializer(variants_qs, many=True).data
    
    def get_images(self, obj):
        request = self.context.get('request')
        print("request: ", request)
        if obj.images:
            return request.build_absolute_uri(obj.images.url) if request else obj.images.url
        return None










# Serializer For Product Landing Page---------------
from rest_framework import serializers
from .models import (
    ProductLandingPage,
    Product,
    ProductVariant,
    ProductImage,
    ProductVideo,
    Category,
    ProductGifting,
)


class CategorySerializer(serializers.ModelSerializer):
    category_path = serializers.ReadOnlyField()

    class Meta:
        model = Category
        fields = "__all__"

class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = "__all__"

    def get_image(self, obj):
        return obj.image.url if obj.image else None

class ProductVideoSerializer(serializers.ModelSerializer):
    video = serializers.SerializerMethodField()

    class Meta:
        model = ProductVideo
        fields = "__all__"

    def get_video(self, obj):
        return obj.video.url if obj.video else None

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = "__all__"

class ProductGiftingSerializer(serializers.ModelSerializer):
    gift_product_name = serializers.CharField(source="gift_product.name",read_only=True)

    class Meta:
        model = ProductGifting
        fields = "__all__"

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    videos = ProductVideoSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    gift_product = ProductGiftingSerializer(many=True, read_only=True)

    primary_image = serializers.ReadOnlyField()
    effective_price = serializers.ReadOnlyField()
    category_path = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = "__all__"

class ProductLandingPageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    og_image = serializers.SerializerMethodField()

    main_product = ProductSerializer(read_only=True)
    products = ProductSerializer(many=True, read_only=True)
    upsell_products = ProductSerializer(many=True, read_only=True)

    class Meta:
        model = ProductLandingPage
        fields = "__all__"

    def get_image(self, obj):
        return obj.image.url if obj.image else None

    def get_og_image(self, obj):
        return obj.og_image.url if obj.og_image else None
# --------------------------------------------------


