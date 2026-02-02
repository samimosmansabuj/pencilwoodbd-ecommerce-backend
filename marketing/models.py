from django.db import models
from pencilwoodbd.choices import EmailConfigServerType, EmailConfigMailType, MarketingIntegrationProviderChoices, MarketingIntegrationStatusChoices

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

