from django.contrib import admin
from .models import Category, Product, AddToCart, FreeAddToCart, ProductImage

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductImage)
admin.site.register(AddToCart)
admin.site.register(FreeAddToCart)

