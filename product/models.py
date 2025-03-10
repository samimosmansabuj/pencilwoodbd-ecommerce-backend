from django.db import models
from authentication.models import Customer
from django.utils.text import slugify
from pencilwoodbd.extra_module import previous_image_delete_os, image_delete_os

def generate_unique_slug(model_object, field_value):
    slug = slugify(field_value)
    unique_slug = slug
    num = 1
    while model_object.objects.filter(slug=unique_slug).exists():
        unique_slug = f'{slug}-{num}'
        num+=1
    return unique_slug

class Category(models.Model):
    title = models.CharField(max_length=100)
    image = models.ImageField(upload_to='category/', blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if self.pk and Category.objects.filter(pk=self.pk).exists():
            old_instance = Category.objects.get(pk=self.pk)
            previous_image_delete_os(old_instance.image, self.image)
        self.slug = generate_unique_slug(Category, self.title)
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        image_delete_os(self.image)
        return super().delete( *args, **kwargs)
    
    def __str__(self):
        return self.title


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, related_name='product_category', null=True, blank=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, null=True)
    short_description = models.TextField(blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    variation = models.CharField(max_length=100, blank=True, null=True)
    stock = models.IntegerField(blank=True, null=True, default=0)
    current_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        self.slug = generate_unique_slug(Product, self.name)
        if self.discount_price is None:
            self.discount_price = self.current_price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_image')
    image = models.ImageField(upload_to='product/')
    
    def save(self, *args, **kwargs):
        if self.pk and ProductImage.objects.filter(pk=self.pk).exists():
            old_instance = ProductImage.objects.get(pk=self.pk)
            previous_image_delete_os(old_instance.image, self.image)
        self.slug = generate_unique_slug(Category, self.title)
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        image_delete_os(self.image)
        return super().delete( *args, **kwargs)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'Product ({self.product.name}) Image'


class AddToCart(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='customer_cart', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name='product_cart', null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if self.product:
            self.price = self.product.current_price
            self.discount_price = self.product.discount_price
            self.total_price = self.quantity * self.discount_price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f'{self.customer} | Cart | {self.product}'
    
    # def save(self, *args, **kwargs):
    #     super().save(*args, **kwargs)
    #     category_products = AddToCart.objects.filter(
    #         customer=self.customer, product__category=self.product.category
    #     ).count()
    #     if category_products % 2 == 0:
    #         FreeAddToCart.objects.create(customer=self.customer, product=self.product)


class FreeAddToCart(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='customer_freecart', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name='product_freecart', null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.customer.name} | Free Cart | {self.product.name}'


