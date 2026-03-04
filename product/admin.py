from django.contrib import admin
from .models import Attribute, AttributeValue, Brand, Category, Product, AddToCart, ProductImage, ProductVariant, ProductVideo, ProductGifting, ProductDeliveryCharge

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'role', 'position')
    readonly_fields = ('created_at', 'updated_at')

class ProductVideoInline(admin.TabularInline):
    model = ProductVideo
    extra = 0
    fields = ('video', 'position')

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    fields = ('sku', 'cost_price', 'price', 'discount_price', 'inventory_quantity', 'attributes', 'is_active')
    readonly_fields = ('sku',)
    extra = 0
    show_change_link = True

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'product_type', 'sku', 'status')
    search_fields = ('title', 'sku')
    inlines = [ProductVariantInline, ProductImageInline, ProductVideoInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', 'sort_order')
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type', 'is_variant', 'is_filterable')
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(AttributeValue)
class AttributeValueAdmin(admin.ModelAdmin):
    list_display = ('id', 'attribute', 'value', 'sort_order')
    list_filter = ('attribute',)
    search_fields = ('value',)

# Models without custom admin
admin.site.register(ProductImage)
admin.site.register(ProductVideo)
admin.site.register(ProductGifting)
admin.site.register(ProductDeliveryCharge)
admin.site.register(AddToCart)
admin.site.register(ProductVariant)