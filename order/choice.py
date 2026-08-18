from django.db import models

class WebhookLogTypeChoice(models.TextChoices):
    delivery_status = 'delivery_status'
    tracking_update = 'tracking_update'


