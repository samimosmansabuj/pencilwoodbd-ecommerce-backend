from rest_framework import serializers
from .models import (
    HomeSlider, SiteContent, SiteColorSection, NewsFeed, SocialLink, FooterTagLink, 
    AboutUs, About_WhyChooseUs, ContactInformation, RefundPolicy, TermsAndCondition, 
    PrivacyPolicy, FAQ_List
)

class HomeSliderSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeSlider
        fields = '__all__'

class SiteContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteContent
        fields = '__all__'

class SiteColorSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteColorSection
        fields = '__all__'

class NewsFeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsFeed
        fields = '__all__'

class SocialLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialLink
        fields = '__all__'

class FooterTagLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = FooterTagLink
        fields = '__all__'

class AboutUsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AboutUs
        fields = '__all__'

class AboutWhyChooseUsSerializer(serializers.ModelSerializer):
    class Meta:
        model = About_WhyChooseUs
        fields = '__all__'

class ContactInformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactInformation
        fields = '__all__'

class RefundPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = RefundPolicy
        fields = '__all__'

class TermsAndConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsAndCondition
        fields = '__all__'

class PrivacyPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivacyPolicy
        fields = '__all__'

class FAQListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ_List
        fields = '__all__'


