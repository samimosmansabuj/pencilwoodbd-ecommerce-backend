from django.utils import timezone
from django.db import models
from pencilwoodbd.choices import EmailConfigServerType, EmailConfigMailType, MarketingIntegrationProviderChoices, MarketingIntegrationStatusChoices
from django.core.validators import MinValueValidator
from decimal import Decimal

class MarketingIntegration(models.Model):
    provider = models.CharField(max_length=64, choices=MarketingIntegrationProviderChoices.choices)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=MarketingIntegrationStatusChoices.choices, default=MarketingIntegrationStatusChoices.ACTIVE)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider} ({self.provider or 'global'})"


class MarketingEventLog(models.Model):
    event_name = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    response = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=64, default='pending')
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_name} for {self.event_name}"


class EmailConfig(models.Model):
    server_type = models.CharField(max_length=25, choices=EmailConfigServerType.choices, default=EmailConfigServerType.SMTP, blank=True, null=True)
    mail_type = models.CharField(max_length=25, choices=EmailConfigMailType.choices, default=EmailConfigMailType.INFO,blank=True, null=True)

    server = models.CharField(blank=True, max_length=50, null=True)
    host_user = models.CharField(max_length=255,blank=True, null=True)
    host_password = models.CharField(max_length=255,blank=True, null=True)
    host = models.CharField(max_length=255, blank=True, null=True)
    port = models.CharField(max_length=10, blank=True, null=True)
    tls = models.BooleanField(default=True)

    email = models.EmailField(max_length=255, blank=True, null=True)
    reply_to = models.EmailField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=50, blank=True, null=True)

    api_key = models.CharField(max_length=500, blank=True, null=True)
    ssl = models.BooleanField(default=False)
    today_count = models.PositiveIntegerField(default=0, blank=True, null=True)
    daily_limit = models.PositiveIntegerField(blank=True, null=True)
    today_date = models.DateField(blank=True, null=True)
    today_complete = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    def increase_today_count(self):
        self.today_count += 1
        if self.today_count == self.daily_limit:
            self.today_complete = True
    
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.email} | {self.host} | LIMIT {self.daily_limit} | Active: {self.is_active}" if self.email else f"{self.server} | {self.api_key}"


class UTMLink(models.Model):
    destination_url = models.URLField(max_length=500)
    platform = models.CharField(max_length=50)   
    medium = models.CharField(max_length=50)     
    campaign = models.CharField(max_length=255)
    generated_url = models.URLField(max_length=1000)
    created_by = models.ForeignKey('authentication.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.campaign} ({self.platform})"
    




class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ("FIXED", "Fixed Amount (৳)"),
        ("PERCENT", "Percentage (%)"),
    ]

    code = models.CharField(max_length=50, unique=True, help_text="e.g. PencilwoodKidz")
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default="FIXED")
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cap for PERCENT type discounts. Leave blank for FIXED or no cap."
    )
    min_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Minimum cart total required for this coupon to apply."
    )

    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(null=True, blank=True, help_text="Leave blank to start immediately.")
    end_date = models.DateTimeField(null=True, blank=True, help_text="Leave blank for no expiry.")

    max_uses_per_phone = models.PositiveIntegerField(
        default=1,
        help_text="How many times a single phone number can use this coupon. E.g. 1 = once per number."
    )
    total_usage_limit = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Overall cap across all customers. Leave blank for unlimited."
    )

    applicable_landing_pages = models.ManyToManyField(
        'site_app.LandingPageProduct', blank=True,
        help_text="Restrict this coupon to specific landing pages. Leave empty = works on ALL landing pages/website."
    )
    applicable_products = models.ManyToManyField(
        'product.Product', blank=True,
        help_text="Restrict this coupon to specific products. Leave empty = works on all products."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code

    def is_currently_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False, "This coupon is not active."
        if self.start_date and now < self.start_date:
            return False, "This coupon is not active yet."
        if self.end_date and now > self.end_date:
            return False, "This coupon has expired."
        if self.total_usage_limit is not None:
            used = self.usages.count()
            if used >= self.total_usage_limit:
                return False, "This coupon has reached its usage limit."
        return True, None

    def is_valid_for_scope(self, landing_page=None, product=None):
        if self.applicable_landing_pages.exists():
            if not landing_page or not self.applicable_landing_pages.filter(id=landing_page.id).exists():
                return False, "This coupon is not valid for this page."
        if self.applicable_products.exists():
            if not product or not self.applicable_products.filter(id=product.id).exists():
                return False, "This coupon is not valid for this product."
        return True, None

    def phone_can_use(self, phone):
        used_count = self.usages.filter(phone=phone).count()
        return used_count < self.max_uses_per_phone

    def calculate_discount(self, subtotal):
        subtotal = Decimal(str(subtotal))
        if subtotal < self.min_order_amount:
            return Decimal("0")
        if self.discount_type == "FIXED":
            discount = self.discount_value
        else:
            discount = subtotal * (self.discount_value / Decimal("100"))
            if self.max_discount_amount is not None:
                discount = min(discount, self.max_discount_amount)
        return min(discount, subtotal)


class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="usages")
    phone = models.CharField(max_length=20)
    order = models.ForeignKey('order.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name="coupon_usage")
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.coupon.code} used by {self.phone}"