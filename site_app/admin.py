from django.contrib import admin
from .models import (
    HomeSlider, SiteContent, SiteColorSection, NewsFeed, SocialLink, FooterTagLink, 
    AboutUs, About_WhyChooseUs, ContactInformation, RefundPolicy, TermsAndCondition, 
    PrivacyPolicy, FAQ_List
)

@admin.register(HomeSlider)
class HomeSliderAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'pk')
    search_fields = ('title',)
    list_filter = ('is_active',)

@admin.register(SiteContent)
class SiteContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'copyright_year')
    search_fields = ('title',)

@admin.register(SiteColorSection)
class SiteColorSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'header', 'footer')
    search_fields = ('title', 'header', 'footer')

@admin.register(NewsFeed)
class NewsFeedAdmin(admin.ModelAdmin):
    list_display = ('news', 'is_active', 'pk')
    search_fields = ('news',)
    list_filter = ('is_active',)

@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'is_active')
    search_fields = ('name', 'url')
    list_filter = ('is_active',)

@admin.register(FooterTagLink)
class FooterTagLinkAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'is_active')
    search_fields = ('name', 'url')
    list_filter = ('is_active',)

@admin.register(AboutUs)
class AboutUsAdmin(admin.ModelAdmin):
    list_display = ('title', 'pk')
    search_fields = ('title',)

@admin.register(About_WhyChooseUs)
class AboutWhyChooseUsAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    search_fields = ('title',)
    list_filter = ('is_active',)

@admin.register(ContactInformation)
class ContactInformationAdmin(admin.ModelAdmin):
    list_display = ('phone', 'email', 'location')
    search_fields = ('phone', 'email', 'location')

@admin.register(RefundPolicy)
class RefundPolicyAdmin(admin.ModelAdmin):
    list_display = ('id',)
    search_fields = ('short_description',)

@admin.register(TermsAndCondition)
class TermsAndConditionAdmin(admin.ModelAdmin):
    list_display = ('id',)
    search_fields = ('short_description',)

@admin.register(PrivacyPolicy)
class PrivacyPolicyAdmin(admin.ModelAdmin):
    list_display = ('id',)
    search_fields = ('short_description',)

@admin.register(FAQ_List)
class FAQListAdmin(admin.ModelAdmin):
    list_display = ('question', 'pk')
    search_fields = ('question',)
