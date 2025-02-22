from django.db import models
from authentication.models import Customer
from django.utils.text import slugify

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
    slug = models.SlugField(unique=True, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        self.slug = generate_unique_slug(Category, self.title)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.title


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, related_name='product_category', null=True, blank=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    variation = models.CharField(max_length=100, blank=True, null=True)
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


class AddToCart(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='customer_cart', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name='product_cart', null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
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


