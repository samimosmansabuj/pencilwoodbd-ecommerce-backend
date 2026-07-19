from rest_framework import serializers
from .models import *


class CategorySerializer(serializers.ModelSerializer):
    category_path = serializers.ReadOnlyField()

    class Meta:
        model = Category
        fields = '__all__'


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'role', 'position']
        read_only_fields = ['id']

    def get_image(self, obj):
        request = self.context.get('request')
        if not obj.image:
            return None
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class ProductVideoSerializer(serializers.ModelSerializer):
    video = serializers.SerializerMethodField()

    class Meta:
        model = ProductVideo
        fields = "__all__"

    def get_video(self, obj):
        request = self.context.get('request')
        if not obj.video:
            return None
        return request.build_absolute_uri(obj.video.url) if request else obj.video.url


class ProductGiftingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductGifting
        fields = ["id", "gift_type", "gift_product", "value", "product"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        gift_product = instance.gift_product
        request = self.context.get('request')

        image_url = None
        if gift_product.primary_image:
            image_url = (
                request.build_absolute_uri(gift_product.primary_image)
                if request else gift_product.primary_image
            )

        data["gift_product"] = {
            "id": gift_product.id,
            "name": gift_product.name,
            "price": gift_product.price,
            "discount_price": gift_product.discount_price,
            "image": image_url,
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
            "sku",
            "price",
            "discount_price",
            "inventory_quantity",
            "attributes",
            "is_active",
            "is_default",
        ]


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    videos = ProductVideoSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    gift_product = ProductGiftingSerializer(many=True, read_only=True)
    delivery_charge = ProductDeliveryChargeSerializer(read_only=True)

    primary_image = serializers.SerializerMethodField()
    effective_price = serializers.ReadOnlyField()
    category_path = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ['id', 'slug', 'delivery_charge', 'gift_product', 'created_at', 'updated_at']

    def get_primary_image(self, obj):
        request = self.context.get('request')
        if not obj.primary_image:
            return None
        return request.build_absolute_uri(obj.primary_image) if request else obj.primary_image


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
        request = self.context.get('request')
        if not obj.image:
            return None
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def get_og_image(self, obj):
        request = self.context.get('request')
        if not obj.og_image:
            return None
        return request.build_absolute_uri(obj.og_image.url) if request else obj.og_image.url


class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeValue
        fields = ["id", "value", "hex_code", "sort_order"]


class AttributeSerializer(serializers.ModelSerializer):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = Attribute
        fields = ["id", "name", "slug", "type", "is_variant", "is_filterable", "values"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]