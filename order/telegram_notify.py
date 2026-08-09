from .models import TelegramBotConfig
from .telegrambot import TelegramBotService


def notify_telegram_for_order(order):
    """
    Call this AFTER the order's items and total_cost are fully committed.
    Safe no-op if no active config exists or the order's source isn't
    in that config's notify_sources list.
    """
    config = TelegramBotConfig.get_active_config()
    if not config or not config.should_notify_for(order.source):
        return
    TelegramBotService.send_order_notification(order, config)