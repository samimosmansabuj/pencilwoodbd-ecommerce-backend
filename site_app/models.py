from typing import Iterable
from django.db import models
from django.conf import settings
from pencilwoodbd.extra_module import image_delete_os, previous_image_delete_os
from product.models import Product, ProductVariant
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from datetime import timedelta
from site_app.bd_districts import SYSTEM_DEFAULT_DELIVERY_CHARGE  

#Fixed One Object Models=============================================
class SiteContent(models.Model):
    title = models.CharField(max_length=55)
    site_slogan = models.CharField(max_length=500, blank=True, null=True)
    logo = models.ImageField(upload_to='logo/', blank=True, null=True)
    secondary_logo = models.ImageField(upload_to='logo/', blank=True, null=True)
    fab_icon = models.ImageField(upload_to='icon/', blank=True, null=True)
    copyright = models.CharField(max_length=55, blank=True, null=True)
    copyright_year = models.CharField(max_length=4, blank=True, null=True)

    # --- Brand identity (used across Dashboard, Invoice, Delivery Token, OTP SMS, etc.) ---
    brand_name = models.CharField(
        max_length=100, blank=True, null=True, default="PencilWoodBD",
        help_text="Main brand name. Shown in dashboard page titles, sidebar, invoice header, delivery token, OTP SMS text, etc."
    )
    brand_short_name = models.CharField(
        max_length=50, blank=True, null=True, default="Pencilwood",
        help_text="Short brand name used in tight spaces like the dashboard sidebar."
    )
    dashboard_title = models.CharField(
        max_length=100, blank=True, null=True, default="PencilWoodBD | Online Shopping",
        help_text="Browser tab title shown on the main dashboard page."
    )
    brand_website = models.CharField(
        max_length=255, blank=True, null=True, default="www.pencilwoodbd.com",
        help_text="Website shown on invoices (e.g. www.example.com)."
    )
    brand_email = models.EmailField(
        max_length=255, blank=True, null=True, default="pencilwoodbd@gmail.com",
        help_text="Support/contact email shown on invoices."
    )
    brand_phone = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="Phone number shown on invoices and delivery tokens (e.g. +8801855942504)."
    )
    invoice_note = models.CharField(
        max_length=255, blank=True, null=True, default="Make all cheques payable to {brand_name}",
        help_text="Note shown on the invoice above the footer. Use {brand_name} as a placeholder if needed."
    )

    def save(self, *args, **kwargs):
        if self.pk and SiteContent.objects.filter(pk=self.pk).exists():
            old_instance = SiteContent.objects.get(pk=self.pk)
            previous_image_delete_os(old_instance.logo, self.logo)
            previous_image_delete_os(old_instance.secondary_logo, self.secondary_logo)
            previous_image_delete_os(old_instance.fab_icon, self.fab_icon)
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        image_delete_os(self.logo)
        image_delete_os(self.secondary_logo)
        image_delete_os(self.fab_icon)
        return super().delete( *args, **kwargs)
    
    def __str__(self):
        return f'{self.title} | {self.pk}'

class SiteColorSection(models.Model):
    title = models.CharField(max_length=55, blank=True, null=True)
    
    news_feed = models.CharField(max_length=55, blank=True, null=True)
    news_feed_text = models.CharField(max_length=55, blank=True, null=True)
    
    header = models.CharField(max_length=55, blank=True, null=True)
    header_taxt = models.CharField(max_length=55, blank=True, null=True)
    header_icon = models.CharField(max_length=55, blank=True, null=True)
    
    slide_run_time = models.PositiveIntegerField(blank=True, null=True)
    
    main_body = models.CharField(max_length=55, blank=True, null=True)
    main_body_title = models.CharField(max_length=55, blank=True, null=True)
    main_body_text = models.CharField(max_length=55, blank=True, null=True)
    
    background = models.CharField(max_length=55, blank=True, null=True)
    background_text = models.CharField(max_length=55, blank=True, null=True)
    
    footer = models.CharField(max_length=55, blank=True, null=True)
    footer_taxt = models.CharField(max_length=55, blank=True, null=True)
    footer_icon = models.CharField(max_length=55, blank=True, null=True)
    
    def __str__(self):
        return f"Default Site Color Section | {self.pk}"

class ContactInformation(models.Model):
    phone = models.CharField(max_length=14)
    secondary_phone = models.CharField(max_length=14, blank=True, null=True)
    whatspp_number = models.CharField(max_length=14, blank=True, null=True)
    email = models.EmailField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"Default Contact Information | {self.pk}"

class RefundPolicy(models.Model):
    short_description = models.TextField(blank=True, null=True)
    descriptin = models.TextField(blank=True, null=True)
    terms_and_conditions = models.TextField(blank=True, null=True)
    exchange_policy = models.TextField(blank=True, null=True)
    refund_policy = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Default Refund Policy Object | {self.pk}"

class TermsAndCondition(models.Model):
    short_description = models.TextField(blank=True, null=True)
    descriptin = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Default Terms & Condition Object | {self.pk}"

class PrivacyPolicy(models.Model):
    short_description = models.TextField(blank=True, null=True)
    descriptin = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Default Privacy Policy Object | {self.pk}"

class AboutUs(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    bg_image = models.ImageField(upload_to='about_us/', blank=True, null=True)
    
    def save(self, *args, **kwargs):
        if self.pk and AboutUs.objects.filter(pk=self.pk).exists():
            old_instance = AboutUs.objects.get(pk=self.pk)
            previous_image_delete_os(old_instance.bg_image, self.bg_image)
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        image_delete_os(self.bg_image)
        return super().delete( *args, **kwargs)
    
    def __str__(self):
        return f'{self.title or None} | {self.pk}'


#Multiple Site Object Models=============================================
class About_WhyChooseUs(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def display_name(self):
        return "Why Choose Us Card"
    
    def __str__(self):
        return f'{self.title} | {self.pk}'

class HomeSlider(models.Model):
    image = models.ImageField(upload_to='slide_image/', null=True)
    title = models.CharField(max_length=55)
    url = models.CharField(max_length=55, blank=True, null=True)
    button_name = models.CharField(max_length=55, blank=True, null=True)
    is_active = models.BooleanField(default=False)  # default False now — admin must explicitly activate
    product = models.ForeignKey('product.Product', on_delete=models.CASCADE,null=True, blank=True, related_name='hero_slides')  

    @property
    def display_name(self):
        return self.product.name if self.product else (self.title or "Slider")

    @property
    def resolved_url(self):
        if self.product:
            return f"/product-details.html?slug={self.product.slug}"
        return self.url or "#"

    def save(self, *args, **kwargs):
        if self.pk and HomeSlider.objects.filter(pk=self.pk).exists():
            old_instance = HomeSlider.objects.get(pk=self.pk)
            previous_image_delete_os(old_instance.image, self.image)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        image_delete_os(self.image)
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f'{self.display_name} | {self.pk}'

class NewsFeed(models.Model):
    news = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']

    @property
    def display_name(self):
        return "News Feed"
    
    def __str__(self):
        return f'{self.news} | {self.pk}'

class SocialLink(models.Model):
    name = models.CharField(max_length=55)
    icon = models.CharField(max_length=20, blank=True, null=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']

    @property
    def display_name(self):
        return "Social Link"
    
    def __str__(self):
        return self.name

class FooterTagLink(models.Model):
    name = models.CharField(max_length=55)
    url = models.CharField(max_length=55, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']

    @property
    def display_name(self):
        return "Footer Tag Link"
    
    def __str__(self):
        return self.name

class NavMenuLink(models.Model):
    name = models.CharField(max_length=55)
    url = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    open_new_tab = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'id']

    @property
    def display_name(self):
        return "Nav Menu Link"

    def __str__(self):
        return self.name

class FAQ_List(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def display_name(self):
        return "FAQ"
    
    def __str__(self):
        return f'{self.question} | {self.pk}'


class LandingPageProduct(models.Model):
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to="landing/", blank=True, null=True)
    code = models.CharField(max_length=30, null=True, blank=True, unique=True)
    main_product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name="landing_page", null=True, blank=True)
    product = models.ManyToManyField(Product, blank=True)
    need_otp_verified = models.BooleanField(default=False)
    area_and_charge = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # ---------------- Per landing page pixel ------------
    enable_pixel_tracking = models.BooleanField(default=True, help_text="If unchecked, Facebook Pixel / GTM / GA4 events for THIS landing page will NOT fire, even if global tracking is ON.")
    facebook_pixel_id = models.CharField(max_length=100, blank=True, null=True, help_text="Optional: override the global Facebook Pixel ID for this landing page only. Leave blank to use the global one.")    
    gtm_container_id = models.CharField(max_length=100, blank=True, null=True)
    ga4_measurement_id = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.title} ({self.code})"


class DeliveryOption(models.Model):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, blank=True, null=True)
    logo = models.FileField(upload_to='delivery_option/', blank=True, null=True, validators=[FileExtensionValidator(allowed_extensions=['svg', 'png', 'jpg', 'jpeg', 'webp'])])
    description = models.TextField(blank=True, null=True)
    api_url = models.CharField(max_length=255, blank=True, null=True)
    api_key = models.CharField(max_length=255, blank=True, null=True)
    secret_key = models.CharField(max_length=255, blank=True, null=True)
    extra_username = models.CharField(max_length=255, blank=True, null=True)
    extra_password = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        if self.type:
            return f'{self.name} - {self.type}'
        return self.name

class WebhookLog(models.Model):
    source = models.CharField(max_length=50)  # 'steadfast' / 'pathao'
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source} webhook - {self.created_at}"

class OTPVerification(models.Model):
    phone = models.CharField(max_length=15)
    otp = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        current_time = timezone.localtime(timezone.now())  # Asia/Dhaka local time
        created_time = timezone.localtime(self.created_at)
        return current_time > created_time + timedelta(minutes=5)

    def __str__(self):
        return f"{self.phone} - {self.otp}"


class SiteDeliveryChargeConfig(models.Model):
    """
    Singleton-style global delivery charge config.
    Used as the fallback when a specific Product has no
    ProductDeliveryCharge (or its area_and_charge is empty/None).

    area_and_charge shape (same convention as ProductDeliveryCharge.area_and_charge):
        {
            "all": 150,        # optional bulk/default value for this scope
            "Dhaka": 80,       # optional per-district overrides
            "Chattogram": 120
        }
    Resolution for a district within ONE scope (product OR global):
        area_and_charge.get(district) if present
        else area_and_charge.get("all") if present
        else None (caller falls through to the next scope)
    """
    area_and_charge = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Global Delivery Charge Config"
        verbose_name_plural = "Global Delivery Charge Config"

    @classmethod
    def get_solo(cls):
        """Always returns the single global config row, creating it if missing."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # never allow deleting the singleton row

    def __str__(self):
        return "Global Delivery Charge Config"
    




class Todo(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_todos'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_todos'
    )
    due_date = models.DateField(blank=True, null=True)
    is_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Reminder(models.Model):
    order = models.ForeignKey(
        'order.Order', on_delete=models.CASCADE, null=True, blank=True, related_name='reminders'
    )
    order_request = models.ForeignKey(
        'order.OrderRequest', on_delete=models.CASCADE, null=True, blank=True, related_name='reminders'
    )
    note = models.TextField()
    remind_date = models.DateField()
    remind_time = models.TimeField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_reminders'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_reminders'
    )
    is_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['remind_date', 'remind_time']

    def __str__(self):
        target = self.order or self.order_request
        return f"Reminder for {target} on {self.remind_date}"


class MaintenanceCost(models.Model):
    class Category(models.TextChoices):
        RENT = 'rent', 'Rent'
        UTILITIES = 'utilities', 'Utilities (Electricity/Gas/Water)'
        SALARY = 'salary', 'Salary / Wages'
        RAW_MATERIALS = 'raw_materials', 'Raw Materials'
        PACKAGING = 'packaging', 'Packaging Materials'
        MARKETING = 'marketing', 'Marketing / Ads'
        EQUIPMENT = 'equipment', 'Equipment / Machinery'
        TRANSPORT = 'transport', 'Transport / Delivery'
        MAINTENANCE_REPAIR = 'maintenance_repair', 'Maintenance / Repair'
        SOFTWARE = 'software', 'Software / Subscription'
        OTHERS = 'others', 'Others'

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        BANK = 'bank', 'Bank Transfer'
        MOBILE_BANKING = 'mobile_banking', 'Mobile Banking (bKash/Nagad)'
        CARD = 'card', 'Card'

    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHERS, blank=True)
    vendor_name = models.CharField(max_length=255, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenance_costs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.name} - {self.amount} ({self.date})"

class DailyProfit(models.Model):
    date = models.DateField(unique=True)
    costs = models.ManyToManyField(MaintenanceCost, blank=True, related_name='daily_profit_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def total_cost(self):
        return sum((cost.amount for cost in self.costs.all()), start=0)

    def __str__(self):
        return f"Daily Profit - {self.date}"


def maintenance_cost_saved(sender, instance, **kwargs):
    """Auto-link a MaintenanceCost to that day's DailyProfit record."""
    daily_profit, _created = DailyProfit.objects.get_or_create(date=instance.date)
    daily_profit.costs.add(instance)


class InvoiceColorConfig(models.Model):
    header_bg = models.CharField(max_length=10, blank=True, null=True, default='#000000')
    footer_bg = models.CharField(max_length=10, blank=True, null=True, default='#000000')
    header_text_color = models.CharField(max_length=10, blank=True, null=True, default='#ffffff')
    footer_text_color = models.CharField(max_length=10, blank=True, null=True, default='#ffffff')
    highlight_color = models.CharField(max_length=10, blank=True, null=True, default='#f5f5f5')
    table_header_text_color = models.CharField(max_length=10, blank=True, null=True, default='#000000')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice Color Config - {self.pk}"

    @classmethod
    def get_config(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
    

class ShowcaseMedia(models.Model):

    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        UPLOADED_VIDEO = 'uploaded_video', 'Uploaded Video'
        EXTERNAL_LINK = 'external_link', 'External Video Link (YouTube/FB/Insta/TikTok)'
        PRODUCT_VIDEO = 'product_video', 'Use Existing Product Video'

    title = models.CharField(max_length=100)
    subtitle = models.CharField(max_length=150, blank=True, null=True)

    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.IMAGE)

    image = models.ImageField(upload_to='showcase/images/', blank=True, null=True)
    video_file = models.FileField(upload_to='showcase/videos/', blank=True, null=True)
    video_url = models.CharField(max_length=500, blank=True, null=True,)
    poster_image = models.ImageField(upload_to='showcase/posters/', blank=True, null=True,
                                      help_text="Thumbnail shown before video plays (optional, recommended for video_url)")

    product_video = models.ForeignKey('product.ProductVideo', on_delete=models.SET_NULL, null=True, blank=True, related_name='showcase_uses')

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', '-id']
        verbose_name = "Showcase Media (See It in Real Life)"
        verbose_name_plural = "Showcase Media (See It in Real Life)"

    @property
    def resolved_video_type(self):
        if not self.video_url:
            return None
        url = self.video_url.lower()
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        if 'facebook.com' in url or 'fb.watch' in url:
            return 'facebook'
        if 'instagram.com' in url:
            return 'instagram'
        if 'tiktok.com' in url:
            return 'tiktok'
        return 'other'

    def save(self, *args, **kwargs):
        if self.pk and ShowcaseMedia.objects.filter(pk=self.pk).exists():
            old = ShowcaseMedia.objects.get(pk=self.pk)
            previous_image_delete_os(old.image, self.image)
            previous_image_delete_os(old.video_file, self.video_file)
            previous_image_delete_os(old.poster_image, self.poster_image)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        image_delete_os(self.image)
        image_delete_os(self.video_file)
        image_delete_os(self.poster_image)
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f'{self.title} ({self.get_media_type_display()}) | {self.pk}'