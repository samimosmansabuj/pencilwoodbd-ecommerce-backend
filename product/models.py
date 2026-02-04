from django.db import models
from authentication.models import Customer
from django.utils.text import slugify
from pencilwoodbd.extra_module import previous_image_delete_os, image_delete_os
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, PRODUCT_TYPE, PRODUCT_MEDIA_TYPE, PRODUCT_MEDIA_ROLE, PRODUCT_GIFT_TYPE
import random, string

def generate_unique_slug(model_object, field_value, old_slug=None):
    slug = slugify(field_value)
    if slug != old_slug:
        unique_slug = slug
        num = 1
        while model_object.objects.filter(slug=unique_slug).exists():
            if unique_slug == old_slug:
                return old_slug
            unique_slug = f'{slug}-{num}'
            num+=1
        return unique_slug
    else:
        return old_slug

def generate_product_sku():
    return ''.join(random.choices(string.digits, k=6))



class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    icon = models.CharField(max_length=10, blank=True, null=True)
    banner_image = models.ImageField(upload_to="category/banner/", blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=CATEGORY_PRODUCT_STATUS.choices, default=CATEGORY_PRODUCT_STATUS.ACTIVE)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        old_slug = Category.objects.get(pk=self.pk) if self.pk else None
        self.slug = generate_unique_slug(Category, self.name, old_slug.slug if old_slug else None)
        return super().save(*args, **kwargs)
    
    @property
    def get_category_path(self):
        path = []
        category = self
        while category:
            path.append(category)
            category = category.parent
        path_string = None
        for p in path:
            if path_string is None:
                path_string = f"{p.name}"
            else:
                path_string += f" -> {p.name}"
        # return list(reversed(path))
        return path_string

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=512)
    slug = models.SlugField(max_length=512, unique=True, blank=True, null=True)
    sku = models.CharField(max_length=128, blank=True, null=True)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE.choices, default=PRODUCT_TYPE.SIMPLE)

    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    short_description = models.TextField(blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    description_json = models.JSONField(default=list, blank=True)

    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    inventory_quantity = models.IntegerField(default=0)

    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    dimensions = models.JSONField(default=dict, blank=True, null=True)

    seo = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=50, choices=CATEGORY_PRODUCT_STATUS.choices, default=CATEGORY_PRODUCT_STATUS.DRAFT)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # @property
    # def active_variante(self):
    #     return self.variants.filter(is_active=True)
    
    @property
    def category_path(self):
        if not self.category:
            return []
        return self.category.get_category_path
    
    @property
    def primary_image(self):
        primary_image = self.images.filter(role=PRODUCT_MEDIA_ROLE.PRIMARY).first()
        if primary_image:
            return primary_image.image.url
        first_image = self.images.first()
        if first_image:
            return first_image.image.url
        return None


    def save(self, *args, **kwargs):
        old_slug = Product.objects.get(pk=self.pk) if self.pk else None
        self.slug = generate_unique_slug(Product, self.name, old_slug.slug if old_slug else None)
        if not self.sku:
            self.sku = generate_product_sku()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    # variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to="product/images/", blank=True, null=True)
    role = models.CharField(max_length=20, choices=PRODUCT_MEDIA_ROLE, default=PRODUCT_MEDIA_ROLE.GALLERY)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def delete(self, *args, **kwargs):
        image_delete_os(self.image)
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        old_instance = ProductImage.objects.get(pk=self.pk) if self.pk else None
        if old_instance:
            previous_image_delete_os(old_instance.image, self.image)
        
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"Image {self.pk} for {self.product.name}"

class ProductVideo(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(upload_to="product/videos/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def delete(self, *args, **kwargs):
        image_delete_os(self.video)
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        old_instance = ProductVideo.objects.get(pk=self.pk) if self.pk else None
        if old_instance:
            previous_image_delete_os(old_instance.video, self.video)
        
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Video {self.pk} for {self.product.name}"

class ProductGifting(models.Model):
    gift_type = models.CharField(max_length=30, choices=PRODUCT_GIFT_TYPE.choices, default=PRODUCT_GIFT_TYPE.FREE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gift_product")
    gift_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="free_product")
    value = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.value} {self.gift_product} {self.gift_type} for per {self.product}"

class ProductDeliveryCharge(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="delivery_charge")
    area_and_charge = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Custom Delivery Charge Set For {self.product}"

# class ProductTag(models.Model):
#     product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_tags')
#     tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='product_tags')

#     def __str__(self):
#         return f"Tag {self.tag.name} for {self.product.title}"

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


