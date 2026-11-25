from django.db.models.signals import post_save
from django.dispatch import receiver

from order.models import Order, OrderAttempt, OrderRequest

from .courier_auto import schedule_auto_check


def _customer_phone(instance):
    return getattr(getattr(instance, "customer", None), "phone", None)


@receiver(post_save, sender=OrderAttempt, dispatch_uid="courier_auto_check_attempt")
def auto_check_attempt(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        schedule_auto_check(instance.phone)


@receiver(post_save, sender=OrderRequest, dispatch_uid="courier_auto_check_order_request")
def auto_check_order_request(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        schedule_auto_check(_customer_phone(instance))


@receiver(post_save, sender=Order, dispatch_uid="courier_auto_check_order")
def auto_check_order(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        schedule_auto_check(_customer_phone(instance))
