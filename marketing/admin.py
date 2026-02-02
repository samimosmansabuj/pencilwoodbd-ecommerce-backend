from django.contrib import admin
from .models import MarketingIntegration, MarketingEventLog, EmailConfig

admin.site.register(MarketingIntegration)
admin.site.register(MarketingEventLog)
admin.site.register(EmailConfig)
