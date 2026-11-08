import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from order.models import Order, OrderItem
from pencilwoodbd.choices import STATUS

# Orders in these statuses are still "pending" (waiting to be booked with a courier)
PENDING_STATUSES = [
    STATUS.NEW,
    STATUS.FOLLOW_UP,
    STATUS.CONFIRMED,
    STATUS.HOLD,
    STATUS.TOKEN_PRINT,
    STATUS.READY_TO_SHIP,
]

# Orders that never count as sales
NOT_SALES_STATUSES = [STATUS.CANCELLED, STATUS.RETURNED, STATUS.REFUNDED, STATUS.RETURN_PROCESSING]


def pending_orders():
    return Order.objects.filter(status__in=PENDING_STATUSES, shipments__isnull=True).distinct()


def product_wise_quantity(order_qs):
    items = (
        OrderItem.objects.filter(order__in=order_qs)
        .select_related("variant")
    )
    rows = {}
    for item in items:
        name = item.display_name
        variant = item.variant_label
        key = (item.product_id, name, variant)
        row = rows.setdefault(key, {"product": name, "variant": variant, "qty": 0, "orders": set()})
        row["qty"] += item.quantity
        row["orders"].add(item.order_id)
    result = []
    for row in rows.values():
        row["orders"] = len(row["orders"])
        result.append(row)
    result.sort(key=lambda r: (-r["qty"], r["product"]))
    return result


def today_orders():
    today = timezone.localdate()
    return Order.objects.filter(created_at__date=today).exclude(status=STATUS.CANCELLED)


ZERO = Decimal("0")
TWO = Decimal("0.01")


def _d(value):
    return Decimal(value) if value is not None else ZERO


def _q(value):
    return _d(value).quantize(TWO)


# Per order figures
def _unit_cost(item):
    if item.variant_id and item.variant and item.variant.cost_price is not None:
        return item.variant.cost_price
    if item.product_id and item.product and item.product.cost_price is not None:
        return item.product.cost_price
    return None


def order_figures(order):
    """All money figures of one order (items must be prefetched).

    items_total : sum(discount_price * qty)   - product value actually charged
    total       : what the customer owes = order.total_cost
                  (items + shipping - coupon - extra discount). If total_cost is
                  empty it is rebuilt from the parts.
    cogs        : sum(cost_price * qty); items with unknown cost are counted in
                  missing_cost_items and add 0 to cogs.
    """
    items_total = ZERO
    cogs = ZERO
    qty = 0
    missing = 0
    for item in order.order_items.all():
        unit = _d(item.discount_price if item.discount_price is not None else item.price)
        items_total += unit * item.quantity
        qty += item.quantity
        cost = _unit_cost(item)
        if cost is None:
            missing += 1
        else:
            cogs += _d(cost) * item.quantity

    shipping = _d(order.shipping_total)
    discount = _d(order.coupon_discount) + _d(order.extra_discount)
    rebuilt = items_total + shipping - discount
    if rebuilt < 0:
        rebuilt = ZERO
    total_cost_missing = order.total_cost is None
    total = rebuilt if total_cost_missing else _d(order.total_cost)

    advance = _d(order.advance_amount)
    due = total - advance
    if due < 0:
        due = ZERO
    return {
        "items_total": items_total,
        "shipping": shipping,
        "discount": discount,
        "total": total,
        "advance": advance,
        "due": due,
        "cogs": cogs,
        "qty": qty,
        "missing_cost_items": missing,
        "total_cost_missing": total_cost_missing,
    }


def _orders_qs():
    return Order.objects.prefetch_related(
        "order_items__variant", "order_items__product"
    )


def _expense_label(category, labels):
    if not category:
        return "Uncategorized"
    return labels.get(category, category)


# Report
def build_report(start, end):
    """Report for start..end (inclusive dates, Asia/Dhaka calendar days).

    Definitions
    -----------
    Valid order        : placed in the period and not cancelled / returned /
                         refunded / return-processing.
    Sales              : sum of order.total_cost of valid orders (shipping included,
                         coupon + extra discount already deducted).
    Product cost       : sum(cost_price * qty) of valid orders' items.
    Estimated profit   : Sales - Product cost - Expense.
    Delivered          : orders delivered in the period (by delivered_at date).
    Realized profit    : Delivered amount - their product cost - Expense.
    Advance            : advance_amount of valid orders.
    Due (to collect)   : total - advance of valid orders that are not delivered yet.
    """
    from site_app.models import MaintenanceCost

    placed = list(
        _orders_qs().filter(created_at__date__gte=start, created_at__date__lte=end)
    )
    valid = [o for o in placed if o.status not in NOT_SALES_STATUSES]
    lost = [o for o in placed if o.status in NOT_SALES_STATUSES]

    delivered = list(
        _orders_qs().filter(
            status=STATUS.DELIVERED,
            delivered_at__date__gte=start,
            delivered_at__date__lte=end,
        )
    )
    delivered_no_date = Order.objects.filter(
        status=STATUS.DELIVERED, delivered_at__isnull=True,
        created_at__date__gte=start, created_at__date__lte=end,
    ).count()

    status_labels = dict(STATUS.choices)
    sums = {k: ZERO for k in ("items_total", "shipping", "discount", "total", "advance", "due", "cogs")}
    qty_total = 0
    missing_cost_items = 0
    total_cost_missing_orders = 0
    due_to_collect = ZERO

    day = {}

    def day_row(d):
        return day.setdefault(d, {
            "date": d, "orders": 0, "sales": ZERO, "advance": ZERO,
            "cogs": ZERO, "expense": ZERO,
        })

    product_rows = {}
    status_rows = {}

    for o in placed:
        f = order_figures(o)
        st = status_rows.setdefault(o.status, {
            "status": status_labels.get(o.status, o.status).replace("_", " ").title(),
            "count": 0, "amount": ZERO,
        })
        st["count"] += 1
        st["amount"] += f["total"]

    for o in valid:
        f = order_figures(o)
        for k in sums:
            sums[k] += f[k]
        qty_total += f["qty"]
        missing_cost_items += f["missing_cost_items"]
        if f["total_cost_missing"]:
            total_cost_missing_orders += 1
        if o.status != STATUS.DELIVERED:
            due_to_collect += f["due"]

        d = day_row(timezone.localtime(o.created_at).date())
        d["orders"] += 1
        d["sales"] += f["total"]
        d["advance"] += f["advance"]
        d["cogs"] += f["cogs"]

        for item in o.order_items.all():
            key = item.display_name
            variant = item.variant_label
            row = product_rows.setdefault((key, variant), {
                "product": key, "variant": variant, "qty": 0,
                "amount": ZERO, "cogs": ZERO, "missing_cost": False,
            })
            unit = _d(item.discount_price if item.discount_price is not None else item.price)
            row["qty"] += item.quantity
            row["amount"] += unit * item.quantity
            cost = _unit_cost(item)
            if cost is None:
                row["missing_cost"] = True
            else:
                row["cogs"] += _d(cost) * item.quantity

    lost_total = ZERO
    lost_advance = ZERO
    for o in lost:
        f = order_figures(o)
        lost_total += f["total"]
        lost_advance += f["advance"]

    delivered_total = ZERO
    delivered_cogs = ZERO
    for o in delivered:
        f = order_figures(o)
        delivered_total += f["total"]
        delivered_cogs += f["cogs"]

    # ---- Expense (Maintenance Cost) ----
    cost_qs = MaintenanceCost.objects.filter(date__gte=start, date__lte=end).order_by("date", "id")
    labels = dict(MaintenanceCost.Category.choices)
    cat = {}
    expense_items = []
    expense_total = ZERO
    for c in cost_qs:
        amount = _d(c.amount)
        expense_total += amount
        label = _expense_label(c.category, labels)
        row = cat.setdefault(label, {"category": label, "total": ZERO, "count": 0})
        row["total"] += amount
        row["count"] += 1
        day_row(c.date)["expense"] += amount
        expense_items.append({
            "date": c.date, "name": c.name, "category": label,
            "vendor": c.vendor_name or "", "amount": amount,
        })
    expense_rows = sorted(cat.values(), key=lambda r: -r["total"])

    day_rows = []
    for d in sorted(day):
        r = day[d]
        r["profit"] = r["sales"] - r["cogs"] - r["expense"]
        day_rows.append(r)

    product_list = sorted(product_rows.values(), key=lambda r: (-r["qty"], r["product"]))
    for r in product_list:
        r["profit"] = r["amount"] - r["cogs"]

    gross_profit = sums["total"] - sums["cogs"]
    return {
        "start": start,
        "end": end,
        "days": (end - start).days + 1,
        "total_orders": len(placed),
        "sales_orders": len(valid),
        "lost_orders": len(lost),
        "lost_total": lost_total,
        "lost_advance": lost_advance,
        "total_qty": qty_total,
        # money
        "items_total": sums["items_total"],
        "shipping_total": sums["shipping"],
        "discount_total": sums["discount"],
        "total_sales": sums["total"],
        "advance_total": sums["advance"],
        "due_to_collect": due_to_collect,
        "product_cost": sums["cogs"],
        "gross_profit": gross_profit,
        "expense_total": expense_total,
        "profit": gross_profit - expense_total,
        "delivered_count": len(delivered),
        "delivered_total": delivered_total,
        "delivered_cost": delivered_cogs,
        "realized_profit": delivered_total - delivered_cogs - expense_total,
        # tables
        "expense_rows": expense_rows,
        "expense_items": expense_items,
        "status_rows": sorted(status_rows.values(), key=lambda r: -r["count"]),
        "product_rows": product_list,
        "day_rows": day_rows,
        # data quality
        "missing_cost_items": missing_cost_items,
        "products_missing_cost": sum(1 for r in product_list if r["missing_cost"]),
        "total_cost_missing_orders": total_cost_missing_orders,
        "delivered_no_date": delivered_no_date,
    }


# Range presets
def _first_of_month(d, back=0):
    """First day of the month `back` months before d's month."""
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def resolve_range(params):
    """?range=week|month|last_month|2m|4m|custom -> (start, end, key, error).

    week        : last 7 days including today
    month       : 1st of this month .. today
    last_month  : the whole previous calendar month
    2m / 4m     : 1st of the month (1 / 3 months back) .. today
                  i.e. this month + previous month(s)
    custom      : start_date..end_date (swapped if reversed)
    """
    today = timezone.localdate()
    key = params.get("range") or "week"
    error = None

    if key == "custom":
        try:
            start = datetime.strptime(params.get("start_date", ""), "%Y-%m-%d").date()
            end = datetime.strptime(params.get("end_date", ""), "%Y-%m-%d").date()
            if start > end:
                start, end = end, start
            return start, end, key, None
        except ValueError:
            error = "Please select a valid start and end date."
            key = "week"

    if key == "month":
        return _first_of_month(today), today, key, error
    if key == "last_month":
        start = _first_of_month(today, 1)
        end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        return start, end, key, error
    if key == "2m":
        return _first_of_month(today, 1), today, key, error
    if key == "4m":
        return _first_of_month(today, 3), today, key, error
    return today - timedelta(days=6), today, "week", error