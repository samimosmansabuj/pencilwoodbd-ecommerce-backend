from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order, TelegramBotConfig
from .telegrambot import TelegramBotService


@receiver(post_save, sender=Order)
def order_created_telegram_notification(sender, instance, created, **kwargs):
    # Disabled: at this exact moment (Order.objects.create), order_items
    # and total_cost are NOT yet committed for any of our creation flows
    # (PlaceOrderAPIView, LandingPageOrderAPI, OrderCreateAPIView, AddOrderView).
    # Each of those views now calls TelegramBotService.send_order_notification()
    # explicitly, after items + total are fully saved.
    return