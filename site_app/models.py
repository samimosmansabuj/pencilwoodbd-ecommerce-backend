from django.db import models
from pencilwoodbd.extra_module import image_delete_os, previous_image_delete_os


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


