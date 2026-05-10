from django.db import models
from authentication.models import Customer
from django.utils.text import slugify
from pencilwoodbd.extra_module import previous_image_delete_os, image_delete_os
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, PRODUCT_TYPE, PRODUCT_MEDIA_TYPE, PRODUCT_MEDIA_ROLE, PRODUCT_GIFT_TYPE, ATTRIBUTE_TYPE
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

class Brand(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    slug = slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    logo = models.ImageField(upload_to="brand/logo/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        old_slug = Brand.objects.get(pk=self.pk) if self.pk else None
        self.slug = generate_unique_slug(Brand, self.name, old_slug.slug if old_slug else None)
        
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Attribute(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    type = models.CharField(max_length=50, choices=ATTRIBUTE_TYPE.choices, default=ATTRIBUTE_TYPE.TEXT)
    is_variant = models.BooleanField(default=False)
    is_filterable = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        old_slug = Attribute.objects.get(pk=self.pk) if self.pk else None
        self.slug = generate_unique_slug(Attribute, self.name, old_slug.slug if old_slug else None)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class AttributeValue(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=255)
    hex_code = models.CharField(max_length=20, blank=True, null=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        unique_together = (('attribute', 'value'),)

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"



class Product(models.Model):
    name = models.CharField(max_length=512)
    slug = models.SlugField(max_length=512, unique=True, blank=True, null=True)
    sku = models.CharField(max_length=128, blank=True, null=False)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE.choices, default=PRODUCT_TYPE.SIMPLE)

    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    short_description = models.TextField(blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    description_json = models.JSONField(default=list, blank=True)

    has_variants = models.BooleanField(default=False)
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
    
    @property
    def active_variants(self):  # New property
        return self.variants.filter(is_active=True) 
    
    @property
    def category_path(self):
        if not self.category:
            return []
        return self.category.get_category_path
    
    @property
    def primary_image(self):
        primary_image = self.images.filter(role=PRODUCT_MEDIA_ROLE.PRIMARY, variant__isnull=True).first()
        if primary_image:
            return primary_image.image.url
        first_image = self.images.first()
        if first_image:
            return first_image.image.url
        return None
    
    @property
    def effective_price(self):
        if self.has_variants:
            first_variant = self.variants.filter(is_active=True).first()
            if first_variant:
                return first_variant.discount_price or first_variant.price
            return 0
        return self.discount_price or self.price


    def save(self, *args, **kwargs):
        is_new = self.pk is None  # NEW

        old_slug = Product.objects.get(pk=self.pk) if self.pk else None
        self.slug = generate_unique_slug(Product, self.name, old_slug.slug if old_slug else None)
        if not self.sku:
            self.sku = generate_product_sku()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ProductVariant(models.Model):  # New model
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')  
    sku = models.CharField(max_length=128,blank=True, null=False)  
    barcode = models.CharField(max_length=128, blank=True, null=True)  
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)  
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)  
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  
    inventory_quantity = models.IntegerField(default=0)  
    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)  
    dimensions = models.JSONField(default=dict, blank=True)  
    attributes = models.JSONField(default=dict, blank=True)  # {"size":"M","color":"Red"}
    is_active = models.BooleanField(default=True)  
    created_at = models.DateTimeField(auto_now_add=True)  
    updated_at = models.DateTimeField(auto_now=True) 

    class Meta:
        unique_together = (('product', 'sku'),)  

    def get_product_sku(self):
        base_sku = self.product.sku or generate_product_sku()
        sku = base_sku

        if self.attributes:
            for key in sorted(self.attributes.keys()):
                value = self.attributes[key]
                sku = f"{sku}-{value}"

        self.sku = sku

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not self.sku:
            self.get_product_sku()
        super().save(*args, **kwargs)

        if is_new and not self.product.has_variants:
            self.product.has_variants = True
            self.product.save(update_fields=["has_variants"])

    def __str__(self):  # new
        return f"{self.product.name} - {self.sku or self.pk}"

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to="product/images/", blank=True, null=True)
    role = models.CharField(max_length=20, choices=PRODUCT_MEDIA_ROLE, default=PRODUCT_MEDIA_ROLE.GALLERY)
    metadata = models.JSONField(default=dict, blank=True) 
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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name='videos')  
    video = models.FileField(upload_to="product/videos/", blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True) 
    position = models.IntegerField(default=0)    
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
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.SET_NULL, related_name='cart_items')      
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):

        if not self.product:
            raise ValueError("Product is required")

        if self.product.has_variants:

            if not self.variant:
                raise ValueError("Variant must be selected")

            if self.variant.product_id != self.product.id:
                raise ValueError("Variant does not belong to this product")

            self.price = self.variant.price
            self.discount_price = self.variant.discount_price
            self.total_price = self.quantity * (
                self.variant.discount_price or self.variant.price
            )

        else:

            self.variant = None
            self.price = self.product.price
            self.discount_price = self.product.discount_price
            self.total_price = self.quantity * (
                self.product.discount_price or self.product.price
            )

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

class Wishlist(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="wishlist"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlisted"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("customer", "product")

    def __str__(self):
        return f"{self.customer} - {self.product}"

