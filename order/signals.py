from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order


@receiver(post_save, sender=Order)
def order_created_telegram_notification(sender, instance, created, **kwargs):
    if not created:
        return
    
    transaction.on_commit(lambda: _send_notification(instance.pk))


def _send_notification(order_id):
    from .models import Order, TelegramBotConfig
    from .telegrambot import TelegramBotService

    order = Order.objects.select_related("customer").prefetch_related(
        "order_items"
    ).get(pk=order_id)

    if not order.source:
        return

    config = TelegramBotConfig.get_active_config()
    if not config or not config.should_notify_for(order.source):
        return

    TelegramBotService.send_order_notification(order, config)