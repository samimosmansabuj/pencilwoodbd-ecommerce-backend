from decimal import Decimal

from django.contrib import messages
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from pencilwoodbd.choices import STATUS, ORDER_REQUEST_STATUS, INVENTORY_TYPE, USER_TYPE

# Models
from order.models import Order, OrderRequest, OrderItem
from product.models import Product
from authentication.models import CustomUser

# Reuse the stock-alert threshold defined alongside the product stock views
from product.views import STOCK_ALERT_THRESHOLD

from order.utils import confirmed_today_filter
from .reports import (
    today_orders, pending_orders, product_wise_quantity, build_report, resolve_range,
    today_orders_by_kind, price_breakdown, grand_total_sum, order_figures,
    TODAY_KINDS, TODAY_KIND_LABELS,
)

class DashboardView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get_today_order_count(self, orders):
        today = timezone.localdate()
        return orders.filter(created_at__date=today).count()

    def get_today_sales_amount(self, orders):
        # Same figure as the "Grand Total" of each order (total_cost): delivery counted once per order,
        # coupon / extra discount already taken off, cancelled orders left out.
        today = timezone.localdate()
        qs = orders.filter(created_at__date=today).exclude(status=STATUS.CANCELLED)
        return grand_total_sum(qs)

    def get_pending_product_qty(self):
        return OrderItem.objects.filter(order__in=pending_orders()).aggregate(
            total=Coalesce(Sum("quantity"), Value(0))
        )["total"]

    def new_orders_count(self, orders):
        return orders.filter(status=STATUS.NEW).count()

    def get_today_confirmed_count(self, orders):
        return orders.filter(confirmed_today_filter()).count()

    def new_order_request_count(self):
        return OrderRequest.objects.filter(
            status=ORDER_REQUEST_STATUS.PENDING
        ).count()

    def get_total_order_amount(self, orders):
        items_total = OrderItem.objects.filter(order__in=orders).aggregate(
            total=Coalesce(
                Sum(F("discount_price") * F("quantity")),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        shipping_total = orders.aggregate(
            total=Coalesce(
                Sum("shipping_total"), Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"]

        final_total = items_total + shipping_total
        return final_total

    def get_status_amounts(self, orders):
        """Total Tk per status, using each order's Grand Total (delivery once per order)."""
        amounts = {}
        for status_key, _ in STATUS.choices:
            amounts[status_key] = grand_total_sum(orders.filter(status=status_key))
        amounts["returned_refund"] = grand_total_sum(orders.filter(status__in=["returned", "refund"]))
        return amounts

    def get_status_counts(self, orders):
        counts = {}
        for status_key, _ in STATUS.choices:
            counts[status_key] = orders.filter(status=status_key).count()

        counts["returned_refund"] = orders.filter(status__in=["returned", "refund"]).count()

        return counts

    def get_urgent_count(self, orders):
        return orders.filter(is_urgent=True).exclude(status__in=[STATUS.DELIVERED, STATUS.CANCELLED, STATUS.RETURNED, STATUS.REFUNDED]).count()

    def get_short_in_stock_count(self):
        return Product.objects.filter(
            inventory_type=INVENTORY_TYPE.IN_STOCK,
            inventory_quantity__gt=0,
            inventory_quantity__lte=STOCK_ALERT_THRESHOLD,
        ).count()

    def get_out_of_stock_count(self):
        return Product.objects.filter(
            Q(inventory_type=INVENTORY_TYPE.OUT_OF_STOCK)
            | Q(inventory_type=INVENTORY_TYPE.IN_STOCK, inventory_quantity__lte=0)
        ).count()

    def get_total_customer_count(self):
        return CustomUser.objects.filter(user_type=USER_TYPE.CUSTOMER).count()

    def get(self, request):
        orders = Order.objects.all().order_by("-created_at")

        is_staff = request.user.user_type == USER_TYPE.STAFF
        is_admin = request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

        context = {
            "orders": orders[:10],
            "today_order_count": self.get_today_order_count(orders),
            "pending_order_count": pending_orders().count(),
            "pending_product_qty": self.get_pending_product_qty(),
            "new_orders_count": self.new_orders_count(orders),
            "today_confirmed_count": self.get_today_confirmed_count(orders),
            "status_amounts": self.get_status_amounts(orders),
            "status_counts": self.get_status_counts(orders),
            "total_orders": orders.count(),
            "new_order_request_count": self.new_order_request_count(),
            "urgent_count": self.get_urgent_count(orders),
            "short_in_stock_count": self.get_short_in_stock_count(),
            "out_of_stock_count": self.get_out_of_stock_count(),
            "total_customer_count": self.get_total_customer_count(),
            "status_choices": STATUS.choices,
        }

        if not is_staff:
            context["total_order_amount"] = self.get_total_order_amount(orders)
            context["today_sales_amount"] = self.get_today_sales_amount(orders)
        else:
            context["total_order_amount"] = None
            context["today_sales_amount"] = None

        if request.htmx:
            return render(request, "db_home/main_wrapper.html", context)

        return render(request, "dashboard.html", context)


class TodayWorkListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        today = timezone.localdate()

        urgent_count = Order.objects.filter(is_urgent=True).exclude(status__in=['delivered', 'cancelled', 'returned', 'refunded']).count()
        today_orders = Order.objects.filter(created_at__date=today)
        today_order_count = today_orders.count()
        total_order_count = Order.objects.count()
        total_order_request_count = OrderRequest.objects.count()
        total_user_count = CustomUser.objects.filter(user_type='customer').count()

        # Raw demand: just today's ordered quantity per product
        product_wise_today = (
            OrderItem.objects.filter(order__created_at__date=today)
            .values('product__name')
            .annotate(qty=Sum('quantity'))
            .order_by('-qty')
        )

        # Inventory comparison: shortfall or remaining stock after fulfilling today's demand
        product_wise_today_ids = (
            OrderItem.objects.filter(order__created_at__date=today)
            .values('product_id', 'product__name')
            .annotate(qty=Sum('quantity'))
            .order_by('-qty')
        )

        inventory_comparison = []
        for row in product_wise_today_ids:
            product = Product.objects.filter(id=row['product_id']).first()
            current_stock = product.inventory_quantity if product else 0
            needed = row['qty']
            shortfall = max(needed - current_stock, 0)
            remaining = max(current_stock - needed, 0)
            inventory_comparison.append({
                'product_name': row['product__name'],
                'needed': needed,
                'current_stock': current_stock,
                'shortfall': shortfall,
                'remaining': remaining,
            })

        context = {
            "urgent_count": urgent_count,
            "today_order_count": today_order_count,
            "total_order_count": total_order_count,
            "total_order_request_count": total_order_request_count,
            "total_user_count": total_user_count,
            "product_wise_today": product_wise_today,
            "inventory_comparison": inventory_comparison,
        }
        return render(request, "db_home/partial/today_work_list.html", context)


class TodayOrderProductsView(LoginRequiredMixin, View):
    """
    Today popup.
    - ?type=received|orders|cancel|confirm  -> which table to look at (just viewing)
    - ?set_default=orders|cancel|confirm    -> remember this box as the user's default (saved in session)
    - ?set_default=none                     -> remove the saved default
    - no type given                         -> the saved default, or All Received when nothing is saved
    """
    login_url = "admin_login"
    SESSION_KEY = "today_popup_default"
    DEFAULT_CHOICES = ("orders", "cancel", "confirm")

    def get(self, request):
        default = request.session.get(self.SESSION_KEY, "")
        if default not in self.DEFAULT_CHOICES:
            default = ""

        set_default = request.GET.get("set_default")
        if set_default in self.DEFAULT_CHOICES:
            default = set_default
            request.session[self.SESSION_KEY] = default
        elif set_default == "none":
            default = ""
            request.session.pop(self.SESSION_KEY, None)

        kind = request.GET.get("type")
        if kind not in TODAY_KINDS:
            kind = default or "received"

        show_money = request.user.user_type != USER_TYPE.STAFF
        view_mode = "breakdown" if (request.GET.get("view") == "breakdown" and show_money) else "list"

        qs = today_orders_by_kind(kind).distinct()
        rows = product_wise_quantity(qs)
        pieces = sum(r["qty"] for r in rows)

        product_lines = []
        if show_money:
            summary = price_breakdown(qs)
            grouped = {}
            for l in summary["lines"]:
                key = (l["product"], l["variant"], l["is_gift"])
                g = grouped.setdefault(key, {
                    "product": l["product"], "variant": l["variant"], "is_gift": l["is_gift"],
                    "qty": 0, "cost": Decimal("0"), "regular": Decimal("0"), "selling": Decimal("0"),
                    "has_cost": False,
                })
                g["qty"] += l["qty"]
                g["regular"] += l["regular"] * l["qty"]
                g["selling"] += l["selling"] * l["qty"]
                if l["cost"] is not None:
                    g["has_cost"] = True
                    g["cost"] += Decimal(l["cost"]) * l["qty"]
            product_lines = sorted(grouped.values(), key=lambda g: (-g["qty"], g["product"]))
        else:
            summary = {"pieces": pieces}

        counts = {k: today_orders_by_kind(k).distinct().count() for k in TODAY_KINDS}

        return render(request, "db_home/partial/today_order_products.html", {
            "kind": kind,
            "kind_label": TODAY_KIND_LABELS[kind],
            "default_kind": default,
            "default_label": TODAY_KIND_LABELS.get(default, TODAY_KIND_LABELS["received"]),
            "counts": counts,
            "rows": rows,
            "product_lines": product_lines,
            "summary": summary,
            "order_count": counts[kind],
            "show_money": show_money,
            "view_mode": view_mode,
            "today": timezone.localdate(),
        })


class PendingProductsView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        qs = pending_orders()
        rows = product_wise_quantity(qs)
        return render(request, "db_home/partial/pending_products.html", {
            "rows": rows,
            "order_count": qs.count(),
            "total_qty": sum(r["qty"] for r in rows),
        })


class SalesReportView(LoginRequiredMixin, View):
    login_url = "admin_login"

    @staticmethod
    def is_allowed(user):
        return user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

    def get(self, request):
        context = {"report_allowed": self.is_allowed(request.user)}

        if context["report_allowed"]:
            start, end, key, error = resolve_range(request.GET)
            if error:
                messages.error(request, error)
            context.update({
                "report": build_report(start, end),
                "range_key": key,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            })

        if request.htmx:
            return render(request, "db_report/partial/partial_sales_report.html", context)

        status = 200 if context["report_allowed"] else 403
        return render(request, "db_report/sales_report.html", context, status=status)


def _csv_safe(value):
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


class SalesReportExportView(SalesReportView):
    def get(self, request):
        import csv
        from django.http import HttpResponse, HttpResponseForbidden

        if not self.is_allowed(request.user):
            return HttpResponseForbidden("Reports are only available for admin.")

        start, end, key, _error = resolve_range(request.GET)
        r = build_report(start, end)
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="report_{start}_{end}.csv"'
        resp.write("\ufeff")
        w = csv.writer(resp)
        w.writerow(["Report", f"{start} to {end}"])
        w.writerow([])
        w.writerow(["Summary"])
        for label, val in [
            ("All orders placed", r["total_orders"]),
            ("Valid orders (not cancelled/returned)", r["sales_orders"]),
            ("Cancelled/returned orders", r["lost_orders"]),
            ("Pieces sold", r["total_qty"]),
            ("Products total", r["items_total"]),
            ("Shipping total", r["shipping_total"]),
            ("Discount (coupon + extra)", r["discount_total"]),
            ("Total sales", r["total_sales"]),
            ("Advance received", r["advance_total"]),
            ("Due to collect (not delivered yet)", r["due_to_collect"]),
            ("Product cost", r["product_cost"]),
            ("Gross profit (sales - product cost)", r["gross_profit"]),
            ("Total expense", r["expense_total"]),
            ("Estimated profit", r["profit"]),
            ("Delivered orders", r["delivered_count"]),
            ("Delivered amount", r["delivered_total"]),
            ("Delivered product cost", r["delivered_cost"]),
            ("Realized profit (delivered - cost - expense)", r["realized_profit"]),
            ("Items with unknown cost price", r["missing_cost_items"]),
        ]:
            w.writerow([label, val])
        w.writerow([])
        w.writerow(["Expense by category"])
        w.writerow(["Category", "Entries", "Amount"])
        for e in r["expense_rows"]:
            w.writerow([e["category"], e["count"], e["total"]])
        w.writerow([])
        w.writerow(["Expense entries"])
        w.writerow(["Date", "Name", "Category", "Vendor", "Amount"])
        for e in r["expense_items"]:
            w.writerow([e["date"], _csv_safe(e["name"]), e["category"], _csv_safe(e["vendor"]), e["amount"]])
        w.writerow([])
        w.writerow(["Product wise"])
        w.writerow(["Product", "Variant", "Pieces", "Sales", "Product cost", "Profit", "Cost missing"])
        for p in r["product_rows"]:
            w.writerow([_csv_safe(p["product"]), _csv_safe(p["variant"]), p["qty"], p["amount"],
                        p["cogs"], p["profit"], "yes" if p["missing_cost"] else ""])
        w.writerow([])
        w.writerow(["Status wise (all orders placed)"])
        w.writerow(["Status", "Orders", "Amount"])
        for s_ in r["status_rows"]:
            w.writerow([s_["status"], s_["count"], s_["amount"]])
        w.writerow([])
        w.writerow(["Day wise"])
        w.writerow(["Date", "Orders", "Sales", "Advance", "Product cost", "Expense", "Profit"])
        for d in r["day_rows"]:
            w.writerow([d["date"], d["orders"], d["sales"], d["advance"], d["cogs"], d["expense"], d["profit"]])
        return resp


class SalesReportExcelView(SalesReportView):

    MONEY = '#,##0.00'
    DATE = 'dd mmm yyyy'

    def get(self, request):
        from io import BytesIO
        from decimal import Decimal
        from django.http import HttpResponse, HttpResponseForbidden
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        if not self.is_allowed(request.user):
            return HttpResponseForbidden("Reports are only available for admin.")

        start, end, key, _error = resolve_range(request.GET)
        r = build_report(start, end)

        head_font = Font(bold=True, color="FFFFFF")
        head_fill = PatternFill("solid", fgColor="1F4E78")
        title_font = Font(bold=True, size=14)
        thin = Side(style="thin", color="BFBFBF")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        def put(ws, row, col, value, fmt=None, bold=False):
            if isinstance(value, Decimal):
                value = float(value)
            cell = ws.cell(row=row, column=col, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
            if fmt:
                cell.number_format = fmt
            if bold:
                cell.font = Font(bold=True)
            cell.border = border
            return cell

        def table(ws, first_row, headers, rows, formats=None):
            """headers: list[str]; rows: list[list]; formats: {col_index: number_format}"""
            formats = formats or {}
            for ci, h in enumerate(headers, start=1):
                c = ws.cell(row=first_row, column=ci, value=h)
                c.font, c.fill, c.border = head_font, head_fill, border
                c.alignment = Alignment(horizontal="center", vertical="center")
            for ri, row in enumerate(rows, start=first_row + 1):
                for ci, v in enumerate(row, start=1):
                    put(ws, ri, ci, v, formats.get(ci))
            return first_row + len(rows) + 1

        def fit(ws, min_w=10, max_w=55):
            widths = {}
            for row in ws.iter_rows():
                for c in row:
                    if c.value is None:
                        continue
                    n = len(str(c.value)) + 2
                    if isinstance(c.value, float):
                        n = len(f"{c.value:,.2f}") + 2
                    widths[c.column] = max(widths.get(c.column, 0), n)
            for col, w in widths.items():
                ws.column_dimensions[get_column_letter(col)].width = max(min_w, min(w, max_w))

        wb = Workbook()

        # ---------------- Summary ----------------
        ws = wb.active
        ws.title = "Summary"
        ws["A1"] = "Sales Report"
        ws["A1"].font = title_font
        ws["A2"] = f"{start:%d %b %Y} to {end:%d %b %Y}  ({r['days']} day{'s' if r['days'] != 1 else ''})"
        money_rows = [
            ("Products total", r["items_total"]),
            ("Shipping total", r["shipping_total"]),
            ("Discount (coupon + extra)", r["discount_total"]),
            ("Total sales", r["total_sales"]),
            ("Advance received", r["advance_total"]),
            ("Due to collect (not delivered yet)", r["due_to_collect"]),
            ("Product cost", r["product_cost"]),
            ("Gross profit (sales - product cost)", r["gross_profit"]),
            ("Total expense", r["expense_total"]),
            ("Estimated profit", r["profit"]),
            ("Delivered amount", r["delivered_total"]),
            ("Delivered product cost", r["delivered_cost"]),
            ("Realized profit (delivered - cost - expense)", r["realized_profit"]),
        ]
        count_rows = [
            ("All orders placed", r["total_orders"]),
            ("Valid orders (not cancelled/returned)", r["sales_orders"]),
            ("Cancelled / returned orders", r["lost_orders"]),
            ("Pieces sold", r["total_qty"]),
            ("Delivered orders", r["delivered_count"]),
            ("Items with unknown cost price", r["missing_cost_items"]),
        ]
        row = 4
        row = table(ws, row, ["Orders & pieces", "Count"], [[a, b] for a, b in count_rows], {2: "0"})
        row += 1
        table(ws, row, ["Money", "Amount (BDT)"], [[a, b] for a, b in money_rows], {2: self.MONEY})
        fit(ws, min_w=14)
        ws.column_dimensions["A"].width = 46

        # ---------------- Product wise ----------------
        ws = wb.create_sheet("Product wise")
        table(ws, 1, ["Product", "Variant", "Pieces", "Sales", "Product cost", "Profit", "Cost missing"],
              [[p["product"], p["variant"] or "-", p["qty"], p["amount"], p["cogs"], p["profit"],
                "yes" if p["missing_cost"] else ""] for p in r["product_rows"]],
              {3: "0", 4: self.MONEY, 5: self.MONEY, 6: self.MONEY})
        ws.freeze_panes = "A2"
        fit(ws)

        # ---------------- Day wise ----------------
        ws = wb.create_sheet("Day wise")
        table(ws, 1, ["Date", "Orders", "Sales", "Advance", "Product cost", "Expense", "Profit"],
              [[d["date"], d["orders"], d["sales"], d["advance"], d["cogs"], d["expense"], d["profit"]]
               for d in r["day_rows"]],
              {1: self.DATE, 2: "0", 3: self.MONEY, 4: self.MONEY, 5: self.MONEY, 6: self.MONEY, 7: self.MONEY})
        ws.freeze_panes = "A2"
        fit(ws, min_w=14)

        # ---------------- Status wise ----------------
        ws = wb.create_sheet("Status wise")
        table(ws, 1, ["Status (all orders placed)", "Orders", "Amount"],
              [[s_["status"], s_["count"], s_["amount"]] for s_ in r["status_rows"]],
              {2: "0", 3: self.MONEY})
        fit(ws, min_w=14)

        # ---------------- Expenses ----------------
        ws = wb.create_sheet("Expenses")
        nxt = table(ws, 1, ["Category", "Entries", "Amount"],
                    [[e["category"], e["count"], e["total"]] for e in r["expense_rows"]],
                    {2: "0", 3: self.MONEY})
        table(ws, nxt + 1, ["Date", "Name", "Category", "Vendor", "Amount"],
              [[e["date"], e["name"], e["category"], e["vendor"], e["amount"]] for e in r["expense_items"]],
              {1: self.DATE, 5: self.MONEY})
        fit(ws, min_w=14)

        buf = BytesIO()
        wb.save(buf)
        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="sales_report_{start}_{end}.xlsx"'
        return resp
