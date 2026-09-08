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


class DashboardView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get_today_order_count(self, orders):
        today = timezone.now().date()
        return orders.filter(created_at__date=today).count()

    def get_today_sales_amount(self, orders):
        today = timezone.now().date()
        return orders.filter(created_at__date=today).aggregate(
            total=Coalesce(Sum(
                F("order_items__discount_price") * F("order_items__quantity") + F("shipping_total")
            ), Value(0), output_field=DecimalField(max_digits=12, decimal_places=2))
        )["total"]

    def new_orders_count(self, orders):
        return orders.filter(status=STATUS.NEW).count()

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
        """Return a dict with total Tk per status"""
        amounts = {}
        for status_key, _ in STATUS.choices:
            amounts[status_key] = orders.filter(status=status_key).aggregate(
                total=Coalesce(
                    Sum(F("order_items__discount_price") * F("order_items__quantity") + F("shipping_total")),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )["total"]

        amounts["returned_refund"] = orders.filter(status__in=["returned", "refund"]).aggregate(
            total=Coalesce(
                Sum(F("order_items__discount_price") * F("order_items__quantity") + F("shipping_total")),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

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
            "new_orders_count": self.new_orders_count(orders),
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


