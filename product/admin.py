from django.contrib import admin
from .models import Category, Product, AddToCart, ProductImage, ProductVideo, ProductGifting, ProductDeliveryCharge

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image',)
    readonly_fields = ('created_at', 'updated_at')

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'discount_price', 'status', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline]

admin.site.register(ProductImage)
admin.site.register(ProductVideo)
admin.site.register(ProductGifting)
admin.site.register(Category)
admin.site.register(Product, ProductAdmin)
admin.site.register(ProductDeliveryCharge)
admin.site.register(AddToCart)

