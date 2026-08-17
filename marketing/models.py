from django.utils import timezone
from django.db import models
from pencilwoodbd.choices import EmailConfigServerType, EmailConfigMailType, MarketingIntegrationProviderChoices, MarketingIntegrationStatusChoices, CouponCustomerConditionChoices, CouponOrderHistoryScopeChoices
from django.core.validators import MinValueValidator
from decimal import Decimal
from order.models import Order
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

    customer_condition = models.CharField(
        max_length=20,
        choices=CouponCustomerConditionChoices.choices,
        default=CouponCustomerConditionChoices.ANY,
    )

    min_previous_orders = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used only when Customer Condition = 'At Least N Previous Orders'"
    )

    order_history_scope = models.CharField(
        max_length=20,
        choices=CouponOrderHistoryScopeChoices.choices,
        default=CouponOrderHistoryScopeChoices.ALL_ORDERS,
    )

    count_orders_before_coupon_creation = models.BooleanField(
        default=True,
        help_text=(
            "If unchecked, only orders placed AFTER this coupon was created "
            "count toward eligibility."
        ),
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

    def is_valid_for_scope(self, landing_page=None, product_ids=None):
        has_landing_restriction = self.applicable_landing_pages.exists()
        has_product_restriction = self.applicable_products.exists()

        if not has_landing_restriction and not has_product_restriction:
            return True, None  

        if landing_page is not None:
            if has_landing_restriction and self.applicable_landing_pages.filter(id=landing_page.id).exists():
                return True, None
            return False, "This coupon is not valid for this page."

        if has_product_restriction:
            product_ids = product_ids or []
            if self.applicable_products.filter(id__in=product_ids).exists():
                return True, None
            return False, "This coupon is not valid for these products."

        return False, "This coupon is not valid for website orders."
    
    def _scoped_product_ids(self):
        product_ids = set(
            self.applicable_products.values_list("id", flat=True)
        )

        for lp in self.applicable_landing_pages.all():
            if lp.main_product_id:
                product_ids.add(lp.main_product_id)

            product_ids.update(
                lp.product.values_list("id", flat=True)
            )

        return product_ids

    def get_relevant_orders_queryset(self, phone):

        qs = Order.objects.filter(customer__phone=phone)

        if not self.count_orders_before_coupon_creation:
            qs = qs.filter(created_at__gte=self.created_at)

        if (
            self.order_history_scope == "SAME_SCOPE"
            and (
                self.applicable_landing_pages.exists()
                or self.applicable_products.exists()
            )
        ):
            product_ids = self._scoped_product_ids()

            qs = qs.filter(
                order_items__product_id__in=product_ids
            ).distinct()

        return qs

    def customer_meets_condition(self, phone):
        if self.customer_condition == "ANY":
            return True, None

        order_count = self.get_relevant_orders_queryset(phone).count()

        if self.customer_condition == "FIRST_ORDER":
            if order_count == 0:
                return True, None

            return False, "This coupon is only for first-time customers."

        if self.customer_condition == "EXISTING":
            if order_count >= 1:
                return True, None

            return False, "This coupon is only for existing customers."

        if self.customer_condition == "MIN_ORDERS":
            required = self.min_previous_orders or 1

            if order_count >= required:
                return True, None

            return False, (
                f"This coupon requires at least "
                f"{required} previous order(s)."
            )

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