import string, secrets
from django.db import models
from authentication.models import Customer
from product.models import Product
from pencilwoodbd.choices import PAYMENT_STATUS, PAYMENT_TYPE, STATUS, REVIEW_STATUS, DELIVERY_TYPE
from datetime import datetime

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
    promotions_applied = models.JSONField(default=dict, blank=True)

    payment_type = models.CharField(max_length=50, choices=PAYMENT_TYPE.choices, default=PAYMENT_TYPE.COD)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS.choices, default=PAYMENT_STATUS.Unpaid)
    
    status = models.CharField(max_length=50, choices=STATUS.choices, default=STATUS.NEW)
    shipping_address = models.CharField(max_length=100, blank=True, null=True)
    
    
    metadata = models.JSONField(default=dict, blank=True)
    delivery_type = models.CharField(max_length=50, choices=DELIVERY_TYPE.choices, default=DELIVERY_TYPE.HOME_DELIVERY)
    delivery_date = models.DateField(null=True, blank=True)
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
    
    def generate_payment_id(self):
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(4))
            today = datetime.now().strftime("%b%d")
            generate_id = f"PWBD-{today.upper()}-{code}"
            if not Order.objects.filter(order_id=generate_id).exists():
                return generate_id

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = self.generate_payment_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.customer} - Order {self.order_id}'

# Order Item Model
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name='order_items', null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def current_total(self):
        return self.price * self.quantity
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f'{self.order} - Order Item - {self.product}'


class Shipment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='shipments')
    courier = models.CharField(max_length=255, blank=True, null=True)
    tracking_number = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default='pending')
    label_url = models.URLField(blank=True, null=True)

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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, related_name="order", blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    title = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=REVIEW_STATUS.choices, default=REVIEW_STATUS.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rating} stars — {self.product}"


