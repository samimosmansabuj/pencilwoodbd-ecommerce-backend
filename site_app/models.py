from typing import Iterable
from django.db import models
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
    is_active = models.BooleanField(default=True)
    
    @property
    def display_name(self):
        return "Slider"

    def save(self, *args, **kwargs):
        if self.pk and HomeSlider.objects.filter(pk=self.pk).exists():
            old_instance = HomeSlider.objects.get(pk=self.pk)
            previous_image_delete_os(old_instance.image, self.image)
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        image_delete_os(self.image)
        return super().delete( *args, **kwargs)
    
    def __str__(self):
        return f'{self.title or None} | {self.pk}'

class NewsFeed(models.Model):
    news = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def display_name(self):
        return "News Feed"
    
    def __str__(self):
        return f'{self.news} | {self.pk}'

class SocialLink(models.Model):
    name = models.CharField(max_length=55)
    icon = models.CharField(max_length=20, blank=True, null=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def display_name(self):
        return "Social Link"
    
    def __str__(self):
        return self.name

class FooterTagLink(models.Model):
    name = models.CharField(max_length=55)
    url = models.CharField(max_length=55, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def display_name(self):
        return "Footer Tag Link"
    
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
    main_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="landing_page", null=True, blank=True)
    product = models.ManyToManyField(Product, blank=True)
    need_otp_verified = models.BooleanField(default=False)
    area_and_charge = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
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
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        if self.type:
            return f'{self.name} - {self.type}'
        return self.name


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