import csv
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views import View

from .models import Order


class OrderExportCSVView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        # ── 1. Parse filters ──────────────────────────────────────────────
        start_date_str = request.GET.get("start_date", "").strip()
        end_date_str   = request.GET.get("end_date", "").strip()
        status_raw     = request.GET.get("status", "all").strip()
        product_slug   = request.GET.get("product", "").strip()

        qs = Order.objects.select_related(
            "customer",
            "coupon",
            "created_by",
            "updated_by",
        ).prefetch_related(
            "order_items__product",
            "order_items__variant",
            "shipments__courier",
        ).order_by("-created_at")

        # Date range
        if start_date_str:
            try:
                start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                qs = qs.filter(created_at__date__gte=start_dt.date())
            except ValueError:
                pass

        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
                qs = qs.filter(created_at__date__lte=end_dt.date())
            except ValueError:
                pass

        # Status filter
        if status_raw and status_raw.lower() != "all":
            statuses = [s.strip() for s in status_raw.split(",") if s.strip()]
            if statuses:
                qs = qs.filter(status__in=statuses)

        # Product filter
        if product_slug:
            qs = qs.filter(order_items__product__slug=product_slug).distinct()

        # ── 2. Build filename ──────────────────────────────────────────────
        today = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"orders_export_{today}.csv"

        # ── 3. Stream CSV response ─────────────────────────────────────────
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)

        # ── 4. Header row ──────────────────────────────────────────────────
        writer.writerow([
            # Order Info-----------------------
            "Order ID",
            "Order Status",
            "Order Date",
            "Order Created Date (Manual)",
            "Delivery Date",
            "Delivered At",
            "Source",
            "Is Urgent",
            
            # Customer Info--------------------
            "Customer Name",
            "Customer Phone",
            "Customer Email",
            
            # Address--------------------------
            "Shipping Address",
            "District",
            "Delivery Type",
            
            # Payment--------------------------
            "Payment Type",
            "Payment Status",
            "Total Cost",
            "Shipping Total",
            "Tax Total",
            "Advance Amount",
            "Due Amount",
            "Coupon Code",
            "Coupon Discount",
            "Extra Discount",
            
            # Marketing-----------------------
            "UTM Source",
            "UTM Medium",
            "UTM Campaign",
            "Referrer",
            
            # Work----------------------------
            "Work Assign",
            "Special Instructions",
            "Note",
            
            # Product Line Items--------------
            "Item #",
            "Product Name",
            "SKU",
            "Variant",
            "Unit Price",
            "Discount Price",
            "Quantity",
            "Item Total (Price x Qty)",
            "Item Total (Discount x Qty)",
            "Is Gift",
            
            # Shipment-----------------------
            "Courier",
            "Tracking Number",
            "Shipment Status",
            
            # Meta---------------------------
            "Created By",
            "Updated By",
            "Created At",
            "Updated At",
        ])

        # ── 5. Data rows (one row per OrderItem) ───────────────────────────
        for order in qs:
            items = list(order.order_items.all())

            shipment        = order.shipments.first()
            courier         = shipment.courier.name if (shipment and shipment.courier) else ""
            tracking_no     = (shipment.tracking_number or "") if shipment else ""
            shipment_status = (shipment.status or "") if shipment else ""

            customer  = order.customer
            cust_name  = customer.name  if customer else ""
            cust_phone = customer.phone if customer else ""
            cust_email = (customer.email if hasattr(customer, "email") else "") if customer else ""

            base_row = [
                # Order Info
                order.order_id or "",
                order.status,
                order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                str(order.order_created_date) if order.order_created_date else "",
                str(order.delivery_date) if order.delivery_date else "",
                order.delivered_at.strftime("%Y-%m-%d %H:%M") if order.delivered_at else "",
                order.source or "",
                "Yes" if order.is_urgent else "No",
                # Customer
                cust_name,
                cust_phone,
                cust_email,
                # Address
                order.shipping_address or "",
                order.district or "",
                order.delivery_type or "",
                # Payment
                order.payment_type or "",
                order.payment_status or "",
                order.total_cost or 0,
                order.shipping_total or 0,
                order.tax_total or 0,
                order.advance_amount or 0,
                order.get_due_amount,
                order.coupon.code if order.coupon else "",
                order.coupon_discount or 0,
                order.extra_discount or 0,
                # Marketing
                order.utm_source or "",
                order.utm_medium or "",
                order.utm_campaign or "",
                order.referrer or "",
                # Work
                order.work_assign or "",
                order.special_instructions or "",
                order.note or "",
            ]

            if items:
                for idx, item in enumerate(items, start=1):
                    writer.writerow(base_row + [
                        idx,
                        item.display_name,
                        item.sku or "",
                        item.variant_label or "",
                        item.price or 0,
                        item.discount_price or 0,
                        item.quantity,
                        item.current_total,
                        item.discount_total_price,
                        "Yes" if item.is_gift else "No",
                        # Shipment
                        courier,
                        tracking_no,
                        shipment_status,
                        # Meta
                        order.created_by.get_full_name() if order.created_by else "",
                        order.updated_by.get_full_name() if order.updated_by else "",
                        order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                        order.updated_at.strftime("%Y-%m-%d %H:%M") if order.updated_at else "",
                    ])
            else:
                # Order with no items — still export the order header row
                writer.writerow(base_row + [
                    "", "", "", "", 0, 0, 1, 0, 0, "No",
                    courier, tracking_no, shipment_status,
                    order.created_by.get_full_name() if order.created_by else "",
                    order.updated_by.get_full_name() if order.updated_by else "",
                    order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                    order.updated_at.strftime("%Y-%m-%d %H:%M") if order.updated_at else "",
                ])

        return response
