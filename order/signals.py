from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order
from django.db.models.signals import post_save, pre_save
from pencilwoodbd.choices import STATUS


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


# ============ IP / DEVICE CANCEL DETECTION SIGNAL ==============

@receiver(pre_save, sender=Order)
def _capture_previous_status(sender, instance, **kwargs):
    """Save hobar age purono status ta instance e temporarily rekhe dei, jate post_save e compare kora jay."""
    if instance.pk:
        try:
            instance._previous_status = Order.objects.only("status").get(pk=instance.pk).status
        except Order.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=Order)
def order_cancel_block_check(sender, instance, created, **kwargs):
    if created:
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status:
        return

    transaction.on_commit(lambda: _sync_track_record_status(instance.pk, instance.status))

    if instance.status != STATUS.CANCELLED:
        return

    transaction.on_commit(lambda: _run_cancel_block_check(instance.pk))


def _sync_track_record_status(order_id, new_status):
    from authentication.models import OrderTrackRecord

    OrderTrackRecord.objects.filter(order_id=order_id).update(status_at_capture=new_status)

def _run_cancel_block_check(order_id):
    from authentication.models import OrderTrackRecord
    from authentication.utils import evaluate_cancel_block
    from order.models import Order

    record = OrderTrackRecord.objects.filter(order_id=order_id).order_by("-created_at").first()
    if not record:
        return

    order = Order.objects.select_related("customer").filter(pk=order_id).first()
    phone = order.customer.phone if order and order.customer else None

    evaluate_cancel_block(record.ip_address, record.device_hash, phone=phone)