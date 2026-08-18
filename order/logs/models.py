# from django.db import models
# from order.choice import WebhookLogTypeChoice

# class SteadFastWebhookLog(models.Model):
#     type = models.CharField(max_length=100, choices=WebhookLogTypeChoice.choices, blank=True, null=True)
#     account = models.CharField(max_length=100, blank=True, null=True)
#     payload = models.JSONField()
#     tracking_message = models.CharField(max_length=255, blank=True, null=True)
#     status = models.CharField(max_length=50, blank=True, null=True)
#     received_at = models.DateTimeField(auto_now_add=True)

#     def save(self, *args, **kwargs):
#         if self.type == WebhookLogTypeChoice.delivery_status:
#             self.status = self.payload.get("status")
#         return super().save(*args, **kwargs)
    
#     def __str__(self):
#         q = f"SteadFast Webhook Log at {self.received_at}"
#         return f"SteadFast {self.type} Webhook Log For {self.account} at {self.received_at}"


