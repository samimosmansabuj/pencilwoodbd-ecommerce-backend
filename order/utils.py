from marketing.models import EmailConfig
from pencilwoodbd.choices import EmailConfigMailType, EmailConfigServerType, USER_TYPE, STATUS, PAYMENT_TYPE, PAYMENT_STATUS, ORDER_SOURCE, DELIVERY_TYPE
from smtplib import SMTP, SMTP_SSL
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from authentication.models import CustomUser
from django.shortcuts import get_object_or_404
from site_app.models import DeliveryOption
import requests, re
from decimal import Decimal, InvalidOperation
import json
from datetime import datetime
from django.db.models import Q
from django.utils import timezone

class OrderConfirmatinoEmailSend:
    def __init__(self, order, email) -> None:
        self.order = order
        self.email = email

    def order_confirmation_mail_send(self):
        email_server = EmailConfig.objects.filter(mail_type=EmailConfigMailType.NO_REPLY, is_active=True).first()
        if email_server.server_type == EmailConfigServerType.SMTP:
            subject = f"Successfully Confirm Your Order #{self.order.order_id}!"
            html_body = self.get_dynamical_block_update(email_server)

            mime_msg = MIMEMultipart('alternative')
            mime_msg['Subject'] = str(Header(subject, 'utf-8'))
            mime_msg['From'] = formataddr((email_server.name, email_server.email))
            mime_msg['To'] = self.email
            mime_msg["Reply-To"] = formataddr(("Samim Osman", email_server.reply_to))
            mime_msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            server = SMTP(host=email_server.host, port=email_server.port)
            server.starttls()
            server.login(email_server.host_user, email_server.host_password)
            print("server login: ", server)
            server.sendmail(
                from_addr=email_server.email, to_addrs=self.email, msg=mime_msg.as_string()
            )
            server.quit()
            return True
        return True
    
    def order_items_template(self):
        order_items_html = ""
        for item in self.order.order_items.all():
            order_items_html += f"""
                <tr>
                    <td style='padding:10px;'>{item.product.name}</td>
                    <td style='padding:10px;'>{item.quantity}</td>
                    <td style='padding:10px;'>৳{item.discount_price}</td>
                </tr>
            """
        return order_items_html
    
    def get_dynamical_block_update(self, email_server):
        user = get_object_or_404(CustomUser, email=self.email, user_type=USER_TYPE.CUSTOMER)
        if user:
            user = user.customer_profile
        order = self.order
        order_items = self.order_items_template()
        msg_body = f"""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Order Confirmation</title>
        </head>
        <body style="margin:0; padding:0; font-family:Arial, Helvetica, sans-serif; background-color:#f4f4f4;">
            <div style="max-width:600px; margin:20px auto; background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">

                <!-- Header -->
                <div style="background:#177484; padding:20px; color:#ffffff; text-align:center;">
                    <h2 style="margin:0; font-size:24px;">Order Confirmation</h2>
                    <p style="margin:5px 0 0;">Thank you for shopping with us!</p>
                </div>

                <!-- Greeting -->
                <div style="padding:20px;">
                    <p style="font-size:16px; margin:0 0 10px;">Dear {user.full_name},</p>
                    <p style="font-size:15px; line-height:1.6; color:#333333;">
                        We’re happy to let you know that your order has been successfully placed.  
                        Below are the details of your order:
                    </p>

                    <!-- Order Info -->
                    <div style="background:#f9f9f9; padding:15px; border-left:4px solid #177484; margin:20px 0; border-radius:5px;">
                        <p style="margin:5px 0; font-size:15px;"><strong>Order ID:</strong> #{order.order_id}</p>
                        <p style="margin:5px 0; font-size:15px;"><strong>Order Date:</strong> {order.placed_at.strftime("%d %B %Y")}</p>
                        <p style="margin:5px 0; font-size:15px;"><strong>Total Amount:</strong> ৳ <span style="text-decoration:line-through; color:#888;">{order.get_current_total }</span> <span style="color:#d32f2f; font-weight:bold; margin-left:5px;">{ order.get_discount_total }</span> ({order.get_discount_percentage}% OFF)</p>
                        <p style="margin:5px 0; font-size:15px;"><strong>Payment Method:</strong> {order.payment_status}</p>
                    </div>

                    <!-- Items Table (Optional)
                    Add if you have order items -->
                    
                    <h3 style="font-size:18px; margin-bottom:10px;">Order Items</h3>
                    <table width="100%" style="border-collapse:collapse;">
                        <tr style="background:#f1f1f1;">
                            <th style="padding:10px; text-align:left;">Product</th>
                            <th style="padding:10px; text-align:left;">Qty</th>
                            <th style="padding:10px; text-align:left;">Price</th>
                        </tr>
                        {order_items}
                    </table>
                    

                    <p style="font-size:15px; margin-top:20px; color:#333;">
                        You will receive another email when your order is shipped.
                    </p>

                    <p style="font-size:15px; margin-top:25px;">
                        If you have any questions, feel free to reply to this email.
                    </p>

                    <p style="font-size:16px; margin-top:20px;"><strong>Best regards,</strong><br>Your Company Team</p>
                </div>

                <!-- Footer -->
                <div style="background:#eeeeee; padding:15px; text-align:center; font-size:12px; color:#555;">
                    &copy; {order.placed_at.year} Your Company. All rights reserved.
                </div>

            </div>
        </body>
        </html>"""

        return msg_body



class SteadFastParcelAPI:
    def __init__(self, id):
        self.id = id
    
    def get_steadfast_credentials(self):
        try:
            steadfast = get_object_or_404(DeliveryOption, id=self.id)
            return steadfast
        except DeliveryOption.DoesNotExist:
            return None

    def create_order(self, order_data):
        url = f"{self.get_steadfast_credentials().api_url}/create_order"
        headers = {
            "Content-Type": "application/json",
            "Api-Key": self.get_steadfast_credentials().api_key,
            "Secret-Key": self.get_steadfast_credentials().secret_key
        }
        response = requests.post(url, headers=headers, json=order_data)
        response.raise_for_status()
        return response.json()

    def delivery_status_checking(self, consignment_id):
        steadfast = self.get_steadfast_credentials()
        url = f"{steadfast.api_url}/status_by_cid/{consignment_id}"
        headers = {
            "Content-Type": "application/json",
            "Api-Key": steadfast.api_key,
            "Secret-Key": steadfast.secret_key
        }
        response = requests.get(url=url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
        # data = response.json()
        # if "delivery_status" not in data:
        #     raise ValueError("Invalid response structure")
        # return True, data.get("delivery_status")

class PathaoParcelAPI:
    def __init__(self, id):
        self.id = id

    def get_pathao_credentials(self):
        try:
            return get_object_or_404(DeliveryOption, id=self.id)
        except DeliveryOption.DoesNotExist:
            return None

    def get_access_token(self):
        partner = self.get_pathao_credentials()
        url = f"{partner.api_url}/aladdin/api/v1/issue-token"
        payload = {
            "client_id": partner.api_key,
            "client_secret": partner.secret_key,
            "grant_type": "password",
            "username": partner.extra_username,
            "password": partner.extra_password, 
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("access_token")

    def create_order(self, order_data):
        partner = self.get_pathao_credentials()
        token = self.get_access_token()
        url = f"{partner.api_url}/aladdin/api/v1/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = json.dumps(
            order_data,
            ensure_ascii=False
        ).encode("utf-8")
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        if not response.ok:
            print("Pathao Status:", response.status_code)
            print("Pathao Response:", response.text)
            print("Pathao Payload:", order_data)
        response.raise_for_status()
        return response.json()
    


def _bill_money(value):
    value = Decimal(str(value or 0))
    return int(value) if value == value.to_integral_value() else float(value)


def build_order_bill(order, request=None):
    from site_app.models import SiteContent, InvoiceColorConfig
    from django.utils import timezone

    site = SiteContent.objects.first()
    colors = InvoiceColorConfig.get_config()

    def abs_url(file_field):
        if not file_field:
            return ""
        try:
            url = file_field.url
        except ValueError:
            return ""
        return request.build_absolute_uri(url) if request else url

    brand_name = (getattr(site, "brand_name", None) or "PencilWoodBD").strip()

    items = []
    subtotal = Decimal("0")
    for item in order.order_items.all().order_by("id"):
        unit = item.discount_price if item.discount_price is not None else (item.price or 0)
        unit = Decimal(str(unit or 0))
        line_total = unit * item.quantity
        subtotal += line_total
        items.append({
            "name": item.display_name,
            "variant": item.variant_label,
            "quantity": item.quantity,
            "unit_price": _bill_money(unit),
            "line_total": _bill_money(line_total),
            "is_free": line_total == 0,
        })

    discount = Decimal(str(order.coupon_discount or 0)) + Decimal(str(order.extra_discount or 0))
    delivery = Decimal(str(order.shipping_total or 0))
    total = order.total_cost if order.total_cost is not None else (subtotal + delivery - discount)

    customer = order.customer
    created = timezone.localtime(order.created_at) if order.created_at else timezone.localtime()

    return {
        "order_id": order.order_id,
        "date": created.strftime("%d %b %Y, %I:%M %p"),
        "payment_type": "Cash on Delivery" if str(order.payment_type).lower() == "cod" else order.get_payment_type_display(),
        "customer": {
            "name": getattr(customer, "name", "") or "",
            "phone": getattr(customer, "phone", "") or "",
            "address": order.shipping_address or "",
            "district": order.district or "",
        },
        "brand": {
            "name": brand_name,
            "logo": abs_url(getattr(site, "logo", None)),
            "website": getattr(site, "brand_website", "") or "",
            "phone": getattr(site, "brand_phone", "") or "",
            "email": getattr(site, "brand_email", "") or "",
        },
        "colors": {
            "header_bg": colors.header_bg or "#000000",
            "header_text": colors.header_text_color or "#ffffff",
            "highlight": colors.highlight_color or "#f5f5f5",
        },
        "items": items,
        "subtotal": _bill_money(subtotal),
        "delivery": _bill_money(delivery),
        "discount": _bill_money(discount),
        "total": _bill_money(total),
    }


def safe_order_bill(order, request=None):
    try:
        return build_order_bill(order, request)
    except Exception:
        return None
    
# ------------------ EXPOSRT UTILS ---------------

# Filters

DATE_FIELDS = {
    "created_at": "created_at__date",
    "delivery_date": "delivery_date",
    "delivered_at": "delivered_at__date",
    "updated_at": "updated_at__date",
}


def get_list(params, key):
    out = []
    for raw in params.getlist(key):
        out += [v.strip() for v in raw.split(",") if v.strip()]
    return out


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal(value):
    try:
        return Decimal((value or "").strip())
    except (InvalidOperation, AttributeError):
        return None


def apply_order_filters(qs, params):
    from .models import OrderItem

    date_lookup = DATE_FIELDS.get(params.get("date_field"), DATE_FIELDS["created_at"])
    start = _parse_date(params.get("start_date"))
    end = _parse_date(params.get("end_date"))
    if start and end and start > end:
        start, end = end, start
    if start:
        qs = qs.filter(**{f"{date_lookup}__gte": start})
    if end:
        qs = qs.filter(**{f"{date_lookup}__lte": end})

    for param, field, valid in (
        ("status", "status", set(STATUS.values)),
        ("payment_type", "payment_type", set(PAYMENT_TYPE.values)),
        ("payment_status", "payment_status", set(PAYMENT_STATUS.values)),
        ("source", "source", set(ORDER_SOURCE.values)),
        ("delivery_type", "delivery_type", set(DELIVERY_TYPE.values)),
    ):
        picked = [v for v in get_list(params, param) if v in valid]
        if picked:
            qs = qs.filter(**{f"{field}__in": picked})

    slugs = get_list(params, "product")
    if slugs:
        qs = qs.filter(
            pk__in=OrderItem.objects.filter(
                Q(product__slug__in=slugs) | Q(variant__product__slug__in=slugs)
            ).values("order_id")
        )

    search = (params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(order_id__icontains=search)
            | Q(customer__name__icontains=search)
            | Q(customer__phone__icontains=search)
            | Q(shipping_address__icontains=search)
            | Q(status__iexact=search)
            | Q(payment_status__iexact=search)
            | Q(delivery_type__iexact=search)
        )

    for param, field in (("updated_by", "updated_by_id"), ("created_by", "created_by_id")):
        val = (params.get(param) or "").strip()
        if val.isdigit():
            qs = qs.filter(**{field: int(val)})

    district = (params.get("district") or "").strip()
    if district:
        qs = qs.filter(district__icontains=district)

    min_total = _parse_decimal(params.get("min_total"))
    max_total = _parse_decimal(params.get("max_total"))
    if min_total is not None:
        qs = qs.filter(total_cost__gte=min_total)
    if max_total is not None:
        qs = qs.filter(total_cost__lte=max_total)

    if params.get("urgent") == "1":
        qs = qs.filter(is_urgent=True)

    return qs


# Row context  (computed once per order, shared by every column)

def _unit_price(item):
    return item.discount_price or item.price or Decimal("0")


class OrderRow:
    def __init__(self, order, no):
        self.order = order
        self.no = no
        self.items = list(order.order_items.all())          # prefetched
        shipments = list(order.shipments.all())             # prefetched
        self.shipment = max(shipments, key=lambda s: s.created_at) if shipments else None
        self.subtotal = sum((_unit_price(i) * i.quantity for i in self.items), Decimal("0"))
        self.qty = sum(i.quantity for i in self.items)


# Column registry

def _money(v):
    return f"{Decimal(v or 0):.2f}"


def _dt(v):
    return timezone.localtime(v).strftime("%Y-%m-%d %H:%M") if v else ""


def _user(u):
    return (u.get_full_name() or u.username) if u else ""


class Column:
    def __init__(self, key, label, group, fn, scope="order", once=False):
        self.key, self.label, self.group = key, label, group
        self.scope = scope
        self.once = once 
        self._fn = fn

    def get(self, r, item, idx):
        if self.scope == "item" and item is None:
            return ""
        return self._fn(r, item, idx)


COLUMNS = {}


def _add(key, label, group, fn, scope="order", once=False):
    COLUMNS[key] = Column(key, label, group, fn, scope, once)


# -- Order
_add("sl", "No.", "Order", lambda r, i, n: r.no)
_add("order_id", "Order ID", "Order", lambda r, i, n: r.order.order_id or "")
_add("status", "Order Status", "Order", lambda r, i, n: r.order.get_status_display())
_add("order_date", "Order Date", "Order", lambda r, i, n: _dt(r.order.created_at))
_add("delivery_date", "Delivery Date", "Order", lambda r, i, n: r.order.delivery_date or "")
_add("delivered_at", "Delivered At", "Order", lambda r, i, n: _dt(r.order.delivered_at))
_add("source", "Source", "Order", lambda r, i, n: r.order.source or "")
_add("order_created_date", "Order Created Date (Manual)", "Order", lambda r, i, n: r.order.order_created_date or "")
_add("is_urgent", "Urgent", "Order", lambda r, i, n: "Yes" if r.order.is_urgent else "No")
_add("products_summary", "Products", "Order",
     lambda r, i, n: "; ".join(
         f"{x.display_name}" + (f" ({x.variant_label})" if x.variant_label else "") + f" x{x.quantity}"
         for x in r.items))

# -- Customer
_add("customer_name", "Customer Name", "Customer", lambda r, i, n: r.order.customer.name if r.order.customer else "")
_add("phone", "Customer Phone", "Customer", lambda r, i, n: (r.order.customer.phone or "") if r.order.customer else "")
_add("second_phone", "Alt Phone", "Customer", lambda r, i, n: (r.order.customer.second_phone or "") if r.order.customer else "")
_add("email", "Customer Email", "Customer", lambda r, i, n: (r.order.customer.email or "") if r.order.customer else "")

# -- Address
_add("address", "Shipping Address", "Address", lambda r, i, n: r.order.shipping_address or "")
_add("district", "District", "Address", lambda r, i, n: r.order.district or "")
_add("delivery_type", "Delivery Type", "Address", lambda r, i, n: r.order.delivery_type or "")

# -- Payment (money columns are `once` so item-layout sums are never doubled)
_add("payment_type", "Payment Type", "Payment", lambda r, i, n: r.order.payment_type or "")
_add("payment_status", "Payment Status", "Payment", lambda r, i, n: r.order.payment_status or "")
_add("items_count", "Line Items", "Payment", lambda r, i, n: len(r.items), once=True)
_add("qty_total", "Total Qty", "Payment", lambda r, i, n: r.qty, once=True)
_add("subtotal", "Items Subtotal", "Payment", lambda r, i, n: _money(r.subtotal), once=True)
_add("tax", "Tax", "Payment", lambda r, i, n: _money(r.order.tax_total), once=True)
_add("shipping", "Shipping", "Payment", lambda r, i, n: _money(r.order.shipping_total), once=True)
_add("coupon_code", "Coupon Code", "Payment", lambda r, i, n: r.order.coupon.code if r.order.coupon else "")
_add("coupon_discount", "Coupon Discount", "Payment", lambda r, i, n: _money(r.order.coupon_discount), once=True)
_add("extra_discount", "Extra Discount", "Payment", lambda r, i, n: _money(r.order.extra_discount), once=True)
_add("total", "Order Total", "Payment", lambda r, i, n: _money(r.order.total_cost), once=True)
_add("advance", "Advance Paid", "Payment", lambda r, i, n: _money(r.order.advance_amount), once=True)
_add("due", "Due Amount", "Payment", lambda r, i, n: _money(r.order.get_due_amount), once=True)

# -- Shipment
_add("courier", "Courier", "Shipment",
     lambda r, i, n: r.shipment.courier.name if r.shipment and r.shipment.courier else "")
_add("tracking", "Tracking No.", "Shipment", lambda r, i, n: (r.shipment.tracking_number or "") if r.shipment else "")
_add("shipment_status", "Shipment Status", "Shipment", lambda r, i, n: (r.shipment.status or "") if r.shipment else "")

# -- Marketing
_add("utm_source", "UTM Source", "Marketing", lambda r, i, n: r.order.utm_source or "")
_add("utm_medium", "UTM Medium", "Marketing", lambda r, i, n: r.order.utm_medium or "")
_add("utm_campaign", "UTM Campaign", "Marketing", lambda r, i, n: r.order.utm_campaign or "")
_add("referrer", "Referrer", "Marketing", lambda r, i, n: r.order.referrer or "")
_add("landing_url", "Landing URL", "Marketing", lambda r, i, n: r.order.landing_url or "")
_add("click_id", "Click ID", "Marketing", lambda r, i, n: r.order.click_id or "")

# -- Work / notes
_add("work_assign", "Work Assign", "Notes", lambda r, i, n: r.order.work_assign or "")
_add("special_instructions", "Special Instructions", "Notes", lambda r, i, n: r.order.special_instructions or "")
_add("note", "Note", "Notes", lambda r, i, n: r.order.note or "")

# -- Meta
_add("created_by", "Created By", "Meta", lambda r, i, n: _user(r.order.created_by))
_add("updated_by", "Updated By", "Meta", lambda r, i, n: _user(r.order.updated_by))
_add("updated_at", "Updated At", "Meta", lambda r, i, n: _dt(r.order.updated_at))

# -- Items (selecting any of these switches to one-row-per-item layout)
_add("item_no", "Item #", "Items", lambda r, i, n: n, scope="item")
_add("product_name", "Product Name", "Items", lambda r, i, n: i.display_name, scope="item")
_add("sku", "SKU", "Items", lambda r, i, n: i.sku or "", scope="item")
_add("variant", "Variant", "Items", lambda r, i, n: i.variant_label, scope="item")
_add("unit_price", "List Price", "Items", lambda r, i, n: _money(i.price), scope="item")
_add("sell_price", "Sell Price", "Items", lambda r, i, n: _money(_unit_price(i)), scope="item")
_add("qty", "Qty", "Items", lambda r, i, n: i.quantity, scope="item")
_add("line_total", "Line Total", "Items", lambda r, i, n: _money(_unit_price(i) * i.quantity), scope="item")
_add("is_gift", "Gift", "Items", lambda r, i, n: "Yes" if i.is_gift else "No", scope="item")


PRESETS = {
    "summary": [
        "sl", "order_id", "status", "order_date", "customer_name", "phone", "district",
        "products_summary", "payment_type", "payment_status", "shipping", "total", "due",
    ],
    "full": [k for k, c in COLUMNS.items() if c.scope == "order"],
    "items": [
        "order_id", "status", "order_date", "customer_name", "phone", "district",
        "product_name", "sku", "variant", "sell_price", "qty", "line_total", "is_gift",
        "shipping", "total",
    ],
}


def get_column_groups():
    """[(group, [(key, label, scope), ...]), ...] for building the modal UI."""
    groups = {}
    for c in COLUMNS.values():
        groups.setdefault(c.group, []).append((c.key, c.label, c.scope))
    return list(groups.items())


def resolve_columns(params):
    """-> (list[Column], layout) where layout is 'order' or 'item'."""
    chosen = [k for k in get_list(params, "cols") if k in COLUMNS]
    if params.get("preset") == "custom" or chosen:
        keys = chosen or PRESETS["summary"]
        columns = [c for c in COLUMNS.values() if c.key in set(keys)]   # canonical order
    else:
        columns = [COLUMNS[k] for k in PRESETS.get(params.get("preset"), PRESETS["summary"])]
    layout = "item" if any(c.scope == "item" for c in columns) else "order"
    return columns, layout


# Rows + CSV safety

_NUMERIC = re.compile(r"^[+-]?[\d.,\s-]+$")


def safe_cell(value):
    """Neutralise spreadsheet formula injection (=, @, +cmd, -cmd) in text cells."""
    if not isinstance(value, str) or not value:
        return value
    if value[0] in ("=", "@", "\t", "\r") or (value[0] in "+-" and not _NUMERIC.match(value)):
        return "'" + value
    return value


def iter_rows(qs, columns, layout):
    yield [c.label for c in columns]
    no = 0
    for order in qs.iterator(chunk_size=500):
        no += 1
        r = OrderRow(order, no)
        if layout == "order":
            yield [c.get(r, None, 0) for c in columns]
        else:
            for idx, item in enumerate(r.items or [None], start=1):
                yield [
                    "" if (c.once and idx > 1) else c.get(r, item, idx)
                    for c in columns
                ]