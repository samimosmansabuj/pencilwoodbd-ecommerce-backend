from django.db import models



class HomeSlider(models.Model):
    image = models.ImageField(upload_to='slide_image/', null=True)
    title = models.CharField(max_length=55)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    url = models.CharField(max_length=55, blank=True, null=True)
    button_name = models.CharField(max_length=55, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f'{self.title or None} | {self.pk}'

class SiteContent(models.Model):
    title = models.CharField(max_length=55)
    site_slogan = models.CharField(max_length=500, blank=True, null=True)
    logo = models.ImageField(upload_to='logo/', blank=True, null=True)
    secondary_logo = models.ImageField(upload_to='logo/', blank=True, null=True)
    fab_icon = models.ImageField(upload_to='icon/', blank=True, null=True)
    copyright = models.CharField(max_length=55, blank=True, null=True)
    copyright_year = models.CharField(max_length=4, blank=True, null=True)
    
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


class NewsFeed(models.Model):
    news = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    def __str__(self):
        return f'{self.news} | {self.pk}'

class SocialLink(models.Model):
    name = models.CharField(max_length=55)
    image = models.ImageField(upload_to='social/', blank=True, null=True)
    icon = models.CharField(max_length=20, blank=True, null=True)
    url = models.URLField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

class FooterTagLink(models.Model):
    name = models.CharField(max_length=55)
    url = models.CharField(max_length=55, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name



class AboutUs(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    bg_image = models.ImageField(upload_to='about_us/', blank=True, null=True)
    
    def __str__(self):
        return f'{self.title or None} | {self.pk}'

class About_WhyChooseUs(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f'{self.title} | {self.pk}'


# =================================Contact Information Start===============================
class ContactInformation(models.Model):
    phone = models.CharField(max_length=14, blank=True, null=True)
    secondary_phone = models.CharField(max_length=14, blank=True, null=True)
    whatspp_number = models.CharField(max_length=14, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
# =================================Contact Information Start===============================

# =================================Refund Policy Start===============================
class RefundPolicy(models.Model):
    short_description = models.TextField(blank=True, null=True)
    descriptin = models.TextField(blank=True, null=True)
    terms_and_conditions = models.TextField(blank=True, null=True)
    exchange_policy = models.TextField(blank=True, null=True)
    refund_policy = models.TextField(blank=True, null=True)
# =================================Refund Policy Start===============================

class TermsAndCondition(models.Model):
    short_description = models.TextField(blank=True, null=True)
    descriptin = models.TextField(blank=True, null=True)

class PrivacyPolicy(models.Model):
    short_description = models.TextField(blank=True, null=True)
    descriptin = models.TextField(blank=True, null=True)


class FAQ_List(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f'{self.question} | {self.pk}'


