from django.db import models
from authentication.models import Customer
from product.models import Product
import uuid

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

# Order Item Model
class OrderItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name='product_orderitem', null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='customer_orderitem', null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    def save(self, *args, **kwargs):
        if not self.price:
            self.price = self.product.discount_price
        if not self.total_price:
            self.total_price = self.product.discount_price * self.quantity
        super().save(*args, **kwargs)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.customer} - Order Item - {self.product}'



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
    PAYMENT_TYPE = (
        ('None', 'None'),
        ('COD', 'COD'),
        ('Online', 'Online'),
        ('Partial', 'Partial'),
    )
    STATUS = (
        ('Pending', 'Pending'),
        ('Confirm', 'Confirm'),
        ('Shipped', 'Shipped'),
        ('Ready to Ship', 'Ready to Ship'),
        ('Out for Delivery', 'Out for Delivery'),
        ('Processing', 'Processing'),
        ('Delivered', 'Delivered'),
        ('Return', 'Return'),
    )
    PAYMENT_STATUS = (
        ('Paid', 'Paid'),
        ('Unpaid', 'Unpaid'),
        ('Partial', 'Partial'),
    )
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, related_name='customer_order', null=True, blank=True)
    order_items = models.ManyToManyField(OrderItem, blank=True, null=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    payment_type = models.CharField(max_length=50, choices=PAYMENT_TYPE, default='COD')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='Unpaid')
    payment_partial = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=STATUS, default='Pending')
    tracking_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    delivery_by = models.CharField(max_length=255, blank=True, null=True)
    
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_payment_method')
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_address')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.pk:
            self.total_cost = sum(i.total_price for i in self.order_items.all())
        
        if not self.tracking_id:
            self.tracking_id = str(uuid.uuid4()).replace("-", "").upper()[:12]  # Generate a unique 12-char tracking ID
        super().save(*args, **kwargs)

    
    def __str__(self):
        return f'{self.customer} - Order {self.tracking_id} - {self.id}'



