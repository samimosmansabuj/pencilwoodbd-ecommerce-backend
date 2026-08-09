from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order, TelegramBotConfig
from .telegrambot import TelegramBotService


@receiver(post_save, sender=Order)
def order_created_telegram_notification(sender, instance, created, **kwargs):
    if not created:
        return

    # source = getattr(instance.customer, "source", None) if instance.customer else None
    # if not source:
    #     return

    config = TelegramBotConfig.get_active_config()
    # if not config or not config.should_notify_for(source):
    #     return

    TelegramBotService.send_order_notification(instance, config)