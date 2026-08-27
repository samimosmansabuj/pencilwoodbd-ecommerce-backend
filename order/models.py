import string, secrets
from django.db import models
from django.forms import ValidationError
from authentication.models import Customer
from product.models import Product, ProductVariant
from pencilwoodbd.choices import ORDER_SOURCE, PAYMENT_STATUS, PAYMENT_TYPE, STATUS, REVIEW_STATUS, DELIVERY_TYPE, ORDER_REQUEST_STATUS, ORDER_REQUEST_WORK_STATUS
from .choice import WebhookLogTypeChoice
from datetime import datetime
from site_app.models import DeliveryOption

# Payment Method Model
class PaymentMethod(models.Model):
    payment_option = models.CharField(max_length=255)
    account_number = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=255, unique=True)
    date_and_time = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.payment_option} | {self.transaction_id}'

# Address Model
class Address(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='customer_address', null=True, blank=True)
    street_01 = models.CharField(max_length=255)
    street_02 = models.CharField(max_length=255, blank=True, null=True)
    upazila = models.CharField(max_length=255)
    post_office = models.CharField(max_length=255, blank=True, null=True)
    post_code = models.CharField(max_length=20, blank=True, null=True)
    district = models.CharField(max_length=255)
    country = models.CharField(max_length=255, default='Bangladesh')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.street_01} - {self.upazila} - {self.district}'


# Order Model
class Order(models.Model):
    order_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='orders', null=True, blank=True)

    shipping_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    advance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    extra_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    promotions_applied = models.JSONField(default=dict, blank=True, null=True)

    payment_type = models.CharField(max_length=50, choices=PAYMENT_TYPE.choices, default=PAYMENT_TYPE.COD)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS.choices, default=PAYMENT_STATUS.Unpaid)

    status = models.CharField(max_length=50, choices=STATUS.choices, default=STATUS.NEW)
    placed_while_blocked = models.BooleanField(default=False)
    shipping_address = models.CharField(max_length=100, blank=True, null=True)

    design_file = models.FileField(upload_to="order/design_files/", blank=True, null=True)
    is_urgent = models.BooleanField(default=False)
    work_assign = models.CharField(max_length=255, blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)
    order_created_date = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=100, blank=True, null=True, choices=ORDER_SOURCE.choices, default=ORDER_SOURCE.OTHERS)

    coupon = models.ForeignKey('marketing.Coupon', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    metadata = models.JSONField(default=dict, blank=True)
    
    # --- Traffic source attribution (marketing) ---
    utm_source = models.CharField(max_length=100, blank=True, null=True)
    utm_medium = models.CharField(max_length=100, blank=True, null=True)
    utm_campaign = models.CharField(max_length=255, blank=True, null=True)
    click_id = models.CharField(max_length=255, blank=True, null=True, help_text="fbclid / ttclid / gclid")
    referrer = models.CharField(max_length=500, blank=True, null=True)
    landing_url = models.CharField(max_length=500, blank=True, null=True)
    
    note = models.TextField(blank=True, null=True)
    delivery_type = models.CharField(max_length=50, choices=DELIVERY_TYPE.choices, default=DELIVERY_TYPE.HOME_DELIVERY)
    delivery_date = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True, help_text="Auto-set the moment status changes to Delivered")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_order_status_choise(self):
        return STATUS.choices
    
    def get_payment_status_choise(self):
        return PAYMENT_STATUS.choices

    @property
    def get_items_total(self):
        product_item = len(self.order_items.all())
        return product_item
    
    @property
    def get_total_quantity(self):
        total_quantity = sum(item.quantity for item in self.order_items.all())
        return total_quantity
    
    @property
    def get_discount_total(self):
        discount_total = sum(item.discount_total_price for item in self.order_items.all())
        return discount_total
    
    @property
    def get_current_total(self):
        current_total = sum(item.current_total for item in self.order_items.all())
        return current_total
    
    @property
    def get_discount_percentage(self):
        if not self.get_discount_total or self.get_discount_total >= self.get_current_total:
            return 0
        discount_amount = self.get_current_total - self.get_discount_total
        discount_percentage = (discount_amount / self.get_current_total) * 100
        return round(discount_percentage, 2)
    
    def generate_order_id(self):
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(4))
            today = datetime.now().strftime("%b%d")
            generate_id = f"PWBD-{today.upper()}-{code}"
            if not Order.objects.filter(order_id=generate_id).exists():
                return generate_id

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = self.generate_order_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.customer} - Order {self.order_id}'

# Order Item Model
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name='order_items', null=True, blank=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    product_name = models.CharField(max_length=255, null=True, blank=True)
    # Snapshot fields
    sku = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    # discount_total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    snapshot = models.JSONField(default=dict, blank=True)

    @property
    def current_total(self):
        return self.price * self.quantity
    
    @property
    def discount_total_price(self):
        return self.discount_price * self.quantity
    

    def save(self, *args, **kwargs):
        if self.variant:
            self.product = self.variant.product
            if not self.product_name:
                self.product_name = self.variant.product.name
            if not self.sku:
                self.sku = self.variant.sku
            if self.price is None:
                self.price = self.variant.price
            if self.discount_price is None:
                self.discount_price = self.variant.discount_price
            if not self.snapshot:
                self.snapshot = {
                    "product_id": self.product.id,
                    "product_name": self.product.name,
                    "variant": self.variant.attributes,
                    "sku": self.variant.sku,
                    "price": str(self.variant.price),
                    "discount_price": str(self.variant.discount_price),
                }
        elif self.product:
            if not self.product_name:
                self.product_name = self.product.name
            if not self.sku:
                self.sku = self.product.sku
            if self.price is None:
                self.price = self.product.price
            if self.discount_price is None:
                self.discount_price = self.product.discount_price
            if not self.snapshot:
                self.snapshot = {
                    "product_id": self.product.id,
                    "product_name": self.product.name,
                    "variant": None,
                    "sku": self.product.sku,
                    "price": str(self.product.price),
                    "discount_price": str(self.product.discount_price),
                }

        # final_price = self.discount_price if self.discount_price else self.price
        # if final_price:
        #     self.discount_total_price = final_price * self.quantity
        super().save(*args, **kwargs)
    
    def clean(self):
        if self.product.has_variants and not self.variant:
            raise ValidationError("Variant is required for this product")

    def __str__(self):
        return f'{self.order} - Order Item - {self.product}'


class Shipment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='shipments')
    courier = models.ForeignKey(DeliveryOption, on_delete=models.SET_NULL, null=True, blank=True, related_name='shipments')
    tracking_number = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default='pending')
    label_url = models.URLField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Shipment {self.courier} for {self.order.order_id}"

class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_payment')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_payment')
    provider = models.CharField(max_length=128)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=50, default='pending')
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    raw_response = models.JSONField(default=dict, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.pk} ({self.provider})"

class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, related_name="order", blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    title = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=REVIEW_STATUS.choices, default=REVIEW_STATUS.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rating} stars — {self.product}"


class OrderRequest(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name="order_requests", null=True, blank=True)

    shipping_address = models.CharField(max_length=255)
    note = models.TextField(blank=True, null=True)

    design_file = models.FileField(upload_to="order_request/design_files/", blank=True, null=True)
    is_urgent = models.BooleanField(default=False)
    work_assign = models.ForeignKey('authentication.CustomUser',on_delete=models.SET_NULL,null=True, blank=True,related_name='assigned_orders')
    special_instructions = models.TextField(blank=True, null=True)
    order_created_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    advance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source = models.CharField(max_length=100, blank=True, null=True, choices=ORDER_SOURCE.choices, default=ORDER_SOURCE.OTHERS)

    payment_type = models.CharField(max_length=50, choices=PAYMENT_TYPE.choices, default=PAYMENT_TYPE.COD)
    delivery_type = models.CharField(max_length=50, choices=DELIVERY_TYPE.choices, default=DELIVERY_TYPE.HOME_DELIVERY)

    shipping_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=ORDER_REQUEST_STATUS.choices, default=ORDER_REQUEST_STATUS.PENDING)
    work_status = models.CharField(max_length=20, choices=ORDER_REQUEST_WORK_STATUS.choices, default=ORDER_REQUEST_WORK_STATUS.NONE)

    converted_order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_request")
    converted_at = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    @property
    def get_items_total(self):
        return self.request_items.count()

    @property
    def get_total_quantity(self):
        return sum(item.quantity for item in self.request_items.all())

    def save(self, *args, **kwargs):
        if self.work_status == ORDER_REQUEST_WORK_STATUS.DONE and self.status == ORDER_REQUEST_STATUS.PENDING:
            self.status = ORDER_REQUEST_STATUS.APPROVED
        super().save(*args, **kwargs)

    def __str__(self):
        if self.customer:
            return f"{self.customer.name} - Request #{self.pk}"
        return f"Order Request #{self.pk}"
    
class OrderRequestItem(models.Model):
    order_request = models.ForeignKey(
        OrderRequest,
        on_delete=models.CASCADE,
        related_name="request_items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_request_items",
    )

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_request_items",
    )

    product_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    sku = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    quantity = models.PositiveIntegerField(
        default=1,
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    discount_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    discount_total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def current_total(self):
        return (self.discount_price or self.price or 0) * self.quantity

    def save(self, *args, **kwargs):

        if self.variant:
            self.product = self.variant.product

            if not self.product_name:
                self.product_name = self.variant.product.name

            if not self.sku:
                self.sku = self.variant.sku

            if self.price is None:
                self.price = self.variant.price

            if self.discount_price is None:
                self.discount_price = self.variant.discount_price

            if not self.snapshot:
                self.snapshot = {
                    "product_id": self.product.id,
                    "product_name": self.product.name,
                    "variant": self.variant.attributes,
                    "sku": self.variant.sku,
                    "price": str(self.variant.price),
                    "discount_price": str(self.variant.discount_price),
                }

        elif self.product:

            if not self.product_name:
                self.product_name = self.product.name

            if not self.sku:
                self.sku = self.product.sku

            if self.price is None:
                self.price = self.product.price

            if self.discount_price is None:
                self.discount_price = self.product.discount_price

            if not self.snapshot:
                self.snapshot = {
                    "product_id": self.product.id,
                    "product_name": self.product.name,
                    "variant": None,
                    "sku": self.product.sku,
                    "price": str(self.product.price),
                    "discount_price": str(self.product.discount_price),
                }

        final_price = self.discount_price if self.discount_price else self.price

        if final_price:
            self.discount_total_price = final_price * self.quantity

        super().save(*args, **kwargs)

    def clean(self):
        if self.product and self.product.has_variants and not self.variant:
            raise ValidationError("Variant is required for this product")

    def __str__(self):
        return f"{self.order_request} - {self.product_name}"
    

class TelegramBotConfig(models.Model):
    name = models.CharField(max_length=100, default="Default Bot", help_text="Just a label, e.g. 'Order Notify Bot'")
    bot_token = models.CharField(max_length=255)
    group_chat_id = models.CharField(max_length=100, help_text="e.g. -1001234567890")
    is_active = models.BooleanField(default=True)

    notify_sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of ORDER_SOURCE values that should trigger a Telegram notification"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram Bot Config"
        verbose_name_plural = "Telegram Bot Configs"

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"

    @classmethod
    def get_active_config(cls):
        return cls.objects.filter(is_active=True).first()

    def should_notify_for(self, source):
        return source in (self.notify_sources or [])

class SteadFastWebhookLog(models.Model):
    type = models.CharField(max_length=100, choices=WebhookLogTypeChoice.choices, blank=True, null=True)
    account = models.CharField(max_length=100, blank=True, null=True)
    payload = models.JSONField()
    tracking_message = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.type == WebhookLogTypeChoice.delivery_status:
            self.status = self.payload.get("status")
        return super().save(*args, **kwargs)
    
    def __str__(self):
        q = f"SteadFast Webhook Log at {self.received_at}"
        return f"SteadFast {self.type} Webhook Log For {self.account} at {self.received_at}"


