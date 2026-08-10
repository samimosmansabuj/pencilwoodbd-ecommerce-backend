import requests
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


class TelegramBotService:

    @classmethod
    def send_order_notification(cls, order, config):
        if not config:
            logger.info("Telegram notification skipped: no config provided.")
            return None

        api_url = f"https://api.telegram.org/bot{config.bot_token}"

        items_lines = []
        for item in order.order_items.all():
            item_total = item.discount_total_price or 0
            items_lines.append(
                f"• {item.product_name} × {item.quantity} — ৳{item_total:,.0f}"
            )
        items_text = "\n".join(items_lines) if items_lines else "N/A"

        customer_name = str(order.customer) if order.customer else "N/A"
        customer_phone = getattr(order.customer, "phone", None) or "N/A"

        phone_display = (
            f"<a href='tel:{customer_phone}'>{customer_phone}</a>"
            if customer_phone != "N/A" else "N/A"
        )

        total_cost = order.total_cost or 0

        local_created_at = timezone.localtime(order.created_at)

        message = (
            f"🛒 <b>NEW ORDER <code>#{order.order_id}</code></b>\n"
            f"📅 {local_created_at.strftime('%d %b %Y, %I:%M %p')}\n"
            f"📌 Status: 🟡 <b>{order.get_status_display()}</b>\n\n"
            f"👤 <b>Customer:</b> {customer_name}\n"
            f"📞 <b>Phone:</b> {phone_display}\n"
            f"📍 <b>Delivery:</b> {order.shipping_address or 'N/A'}\n\n"
            f"🛍️ <b>Items:</b>\n"
            f"{items_text}\n\n"
            f"💰 <b>Total:</b> ৳{total_cost:,.0f}\n"
            f"💳 <b>Payment:</b> {order.get_payment_type_display()}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <b>ACTION REQUIRED</b>"
        )

        view_query = customer_phone.lstrip("+")
        if view_query.startswith("880"):
            view_query = "0" + view_query[3:]

        payload = {
            "chat_id": config.group_chat_id,
            "parse_mode": "HTML",
            "text": message,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "🙋 Assign Myself",
                            "callback_data": f"assign_staff:{order.id}"
                        },
                        {
                            "text": "👁 View Order",
                            "url": f"https://api.pencilwoodbd.org/order-list/?q={view_query}"
                        }
                    ]
                ]
            }
        }

        try:
            response = requests.post(f"{api_url}/sendMessage", json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Telegram notification failed for order {order.order_id}: {e}")
            return None