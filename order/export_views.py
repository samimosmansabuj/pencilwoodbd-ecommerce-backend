import csv
from collections import defaultdict

from django.http import JsonResponse
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from .models import Order


class OrderExportCSVView(LoginRequiredMixin, View):
    _BLANK_ORDER_FIELDS = 26
    
    def get_payment_col(self):
        # "Total Sale (Order Total Cost)",  # 17  ← what the customer pays
        # "Product Items Cost (Sum)",      # 18  ← sum of all item price×qty
        # "Shipping Total",                # 19
        # "Tax Total",                     # 20
        # "Advance Amount",                # 21
        # "Due Amount",                    # 22
        # "Coupon Code",                   # 23
        # "Coupon Discount",               # 24
        # "Extra Discount",                # 25
        return [
            # ── PAYMENT  (order-level — do NOT sum across rows!)
            # "Payment Type",                  # 15
            # "Payment Status",                # 16
            "Order Item",
            "Item Total (Price × Qty)",      # 17
            "Shipping Total",                # 18
            "Coupon Code",                   # 19
            "Coupon Discount",               # 20
            "Extra Discount",                # 21
            "Total Sales (Order Total Cost)",  # 22  ← what the customer pays
            "Product Items Cost (Sum)",      # 23
        ]
        
    def get_marketing_col(self):
        return [
            # ── MARKETING
            "UTM Source",                    # 26
            "UTM Medium",                    # 27
            "UTM Campaign",                  # 28
            "Referrer",                      # 29
        ]
    
    def get_work_col(self):
        return [
            # ── WORK
            "Work Assign",                   # 30
            "Special Instructions",          # 31
            "Note",                          # 32
        ]
    
    def get_meta_col(self):
            return [
            # ── META (appear once per order, blank on extra item rows)
            "Created By",                    # 33
            "Updated By",                    # 34
            "Created At",                    # 35
            "Updated At",                    # 36
        ]
    
    def get_item_col(self):
        # ═══════════════════════════════════════════════════════════════
        return [
            # ── ITEM COLUMNS  (change every row — safe to sum)
            "Item #",                        # 37
            "Product Name",                  # 38
            "SKU",                           # 39
            "Variant",                       # 40
            "Unit Price",                    # 41
            "Discount Price",                # 42
            "Quantity",                      # 43
            "Item Total (Price × Qty)",      # 44
            "Item Total (Discount × Qty)",   # 45
            "Is Gift",                       # 46
            
            # ── SHIPMENT
            # "Courier",                       # 47
            # "Tracking Number",               # 48
            # "Shipment Status",               # 49
        ]
    
    def get_header_list(self):
        h_list = [
            # ── ORDER INFO (appear once per order, blank on extra item rows)
            "No.",                           # 0
            "Order ID",                      # 1
            "Order Status",                  # 2
            "Order Date",                    # 3
            # "Order Created Date (Manual)",   # 4
            # "Delivery Date",                 # 5
            # "Delivered At",                  # 6
            # "Source",                        # 7
            # "Is Urgent",                     # 8
            
            # ── CUSTOMER
            "Customer Name",                 # 9
            "Customer Phone",                # 10
            # "Customer Email",                # 11
            
            # ── ADDRESS
            # "Shipping Address",              # 12
            # "District",                      # 13
            # "Delivery Type",                 # 14
        ]
        
        h_list += self.get_payment_col()
        # h_list += self.get_marketing_col()
        # h_list += self.get_work_col()
        # h_list += self.get_meta_col()
        # h_list += self.get_item_col()
        
        return h_list

    def get(self, request, *args, **kwargs):
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
        today    = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"orders_export_{today}.csv"

        # ── 3. HTTP response ───────────────────────────────────────────────
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)

        # ── 4. Header ──────────────────────────────────────────────────────
        header_list = self.get_header_list()
        writer.writerow(header_list)

        # ── 5. Data rows ───────────────────────────────────────────────────
        row_no = 0
        for order in qs:
            row_no += 1
            items = list(order.order_items.all())

            # Shipment
            shipment        = order.shipments.first()
            courier         = shipment.courier.name if (shipment and shipment.courier) else ""
            tracking_no     = (shipment.tracking_number or "") if shipment else ""
            shipment_status = (shipment.status or "") if shipment else ""

            # Customer
            customer   = order.customer
            cust_name  = customer.name  if customer else ""
            cust_phone = customer.phone if customer else ""
            cust_email = (customer.email if hasattr(customer, "email") else "") if customer else ""

            # Product Items Total Cost = sum of all item (price × qty)
            item_total = sum((item.discount_price or 0) * item.quantity for item in items)
            item_total_cost = 0
            for item in items:
                if item.variant:
                    item_total_cost += (item.variant.cost_price or 0) * item.quantity
                elif item.product:
                    item_total_cost += (item.product.cost_price or 0) * item.quantity
            

            # ── Order-level columns (written only in the first item's row)
            order_cells = [
                row_no,
                order.order_id or "",
                order.status,
                order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                # str(order.order_created_date) if order.order_created_date else "",
                # str(order.delivery_date) if order.delivery_date else "",
                # order.delivered_at.strftime("%Y-%m-%d %H:%M") if order.delivered_at else "",
                # order.source or "",
                # "Yes" if order.is_urgent else "No",
                
                # Customer
                cust_name,
                cust_phone,
                # cust_email,
                
                # Address
                # order.shipping_address or "",
                # order.district or "",
                # order.delivery_type or "",
                
                # Payment
                len(items),  # Number of items
                item_total,
                order.shipping_total or 0,
                order.coupon.code if order.coupon else "",
                order.coupon_discount or 0,
                order.extra_discount or 0,
                order.total_cost or 0,
                item_total_cost,
                
                # Marketing
                # order.utm_source or "",
                # order.utm_medium or "",
                # order.utm_campaign or "",
                # order.referrer or "",
                
                # Work
                # order.work_assign or "",
                # order.special_instructions or "",
                # order.note or "",
                
                # Meta
                # order.created_by.get_full_name() if order.created_by else "",
                # order.updated_by.get_full_name() if order.updated_by else "",
                # order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                # order.updated_at.strftime("%Y-%m-%d %H:%M") if order.updated_at else "",
            ]

            # Blank version — same length, all empty strings
            # Used for item rows 2, 3, … so order totals are not duplicated
            # blank_order_cells = [""] * len(order_cells)

            # # Shipment + item trailing columns
            # def item_cells(idx, item):
            #     return [
            #         idx,
            #         item.display_name,
            #         item.sku or "",
            #         item.variant_label or "",
            #         item.price or 0,
            #         item.discount_price or 0,
            #         item.quantity,
            #         item.current_total,
            #         item.discount_total_price,
            #         "Yes" if item.is_gift else "No",
            #         # courier,
            #         # tracking_no,
            #         # shipment_status,
            #     ]

            # if items:
            #     for idx, item in enumerate(items, start=1):
            #         # First item → full order info; subsequent → blanks
            #         row_prefix = order_cells if idx == 1 else blank_order_cells
            #         writer.writerow(row_prefix + item_cells(idx, item))
            # else:
            #     # No items at all — write one row with blanks in item columns
            #     writer.writerow(order_cells + [
            #         "", "", "", "", 0, 0, 0, 0, 0, "No",
            #         # courier, tracking_no, shipment_status,
            #     ])
            writer.writerow(order_cells)

        return response


class OrderProductRequirementView(LoginRequiredMixin, View):
    """
    Returns a JSON list that shows, for the given status/product filters,
    how many units of each product variant are required across all matching orders.

    Response shape:
    {
        "success": true,
        "filters": { "status": [...], "product": "slug" },
        "items": [
            {
                "product_name": "...",
                "sku": "...",
                "variant": "Size: L / Color: Red",
                "total_quantity": 42,
                "total_sale_amount": 25200.00
            },
            ...
        ],
        "grand_total_qty": 120,
        "grand_total_amount": 75000.00
    }
    """

    def get(self, request, *args, **kwargs):
        status_raw   = request.GET.get("status", "all").strip()
        product_slug = request.GET.get("product", "").strip()

        from .models import OrderItem

        qs = OrderItem.objects.select_related(
            "order",
            "product",
            "variant",
        ).filter(
            order__isnull=False,
        )

        # Status filter
        if status_raw and status_raw.lower() != "all":
            statuses = [s.strip() for s in status_raw.split(",") if s.strip()]
            if statuses:
                qs = qs.filter(order__status__in=statuses)

        # Product filter
        if product_slug:
            qs = qs.filter(product__slug=product_slug)

        # ── Aggregate ────────────────────────────────────────────────────
        # Key: (product_name, sku, variant_label)
        aggregated = defaultdict(lambda: {"total_quantity": 0, "total_sale_amount": 0})

        for item in qs:
            product_name = item.display_name
            sku          = item.sku or ""
            variant_lbl  = item.variant_label or "—"

            key = (product_name, sku, variant_lbl)
            aggregated[key]["total_quantity"]   += item.quantity
            aggregated[key]["total_sale_amount"] += float(
                (item.discount_price or item.price or 0) * item.quantity
            )

        # Sort by product name then variant
        result = []
        for (product_name, sku, variant_lbl), data in sorted(aggregated.items()):
            result.append({
                "product_name":      product_name,
                "sku":               sku,
                "variant":           variant_lbl,
                "total_quantity":    data["total_quantity"],
                "total_sale_amount": round(data["total_sale_amount"], 2),
            })

        grand_total_qty    = sum(r["total_quantity"]    for r in result)
        grand_total_amount = round(sum(r["total_sale_amount"] for r in result), 2)

        return JsonResponse({
            "success": True,
            "filters": {
                "status":  status_raw,
                "product": product_slug,
            },
            "items":               result,
            "grand_total_qty":     grand_total_qty,
            "grand_total_amount":  grand_total_amount,
        })


class OrderShortDetailView(LoginRequiredMixin, View):
    """
    Returns a lightweight JSON snapshot of a single order for the quick-view modal.

    GET /orders/<id>/short-detail/
    """

    def get(self, request, pk, *args, **kwargs):
        order = get_object_or_404(
            Order.objects.select_related("customer", "coupon", "updated_by", "created_by")
                         .prefetch_related("order_items__product", "order_items__variant",
                                           "shipments__courier"),
            pk=pk,
        )

        customer = order.customer

        # ── Items ─────────────────────────────────────────────────────────
        items = []
        for item in order.order_items.all():
            items.append({
                "name":           item.display_name,
                "sku":            item.sku or "",
                "variant":        item.variant_label or "",
                "qty":            item.quantity,
                "unit_price":     float(item.price or 0),
                "discount_price": float(item.discount_price or 0),
                "item_total":     float(item.discount_total_price or item.current_total or 0),
                "is_gift":        item.is_gift,
            })

        # ── Shipment ──────────────────────────────────────────────────────
        shipment = order.shipments.first()
        shipment_data = None
        if shipment:
            shipment_data = {
                "courier":        shipment.courier.name if shipment.courier else "",
                "tracking":       shipment.tracking_number or "",
                "status":         shipment.status or "",
            }

        # ── Response ──────────────────────────────────────────────────────
        return JsonResponse({
            "success": True,
            "order": {
                "id":               order.id,
                "order_id":         order.order_id or "",
                "status":           order.status,
                "source":           order.source or "",
                "is_urgent":        order.is_urgent,
                "payment_type":     order.payment_type or "",
                "payment_status":   order.payment_status or "",
                "delivery_type":    order.delivery_type or "",
                "delivery_date":    str(order.delivery_date) if order.delivery_date else "",
                "note":             order.note or "",
                "special_instructions": order.special_instructions or "",
                "work_assign":      order.work_assign or "",
                # totals
                "total_cost":       float(order.total_cost or 0),
                "shipping_total":   float(order.shipping_total or 0),
                "advance_amount":   float(order.advance_amount or 0),
                "due_amount":       float(order.get_due_amount),
                "coupon_code":      order.coupon.code if order.coupon else "",
                "coupon_discount":  float(order.coupon_discount or 0),
                "extra_discount":   float(order.extra_discount or 0),
                # customer
                "customer_name":    customer.name if customer else "",
                "customer_phone":   customer.phone if customer else "",
                "customer_email":   (customer.email if hasattr(customer, "email") else "") if customer else "",
                # address
                "shipping_address": order.shipping_address or "",
                "district":         order.district or "",
                # dates
                "created_at":       order.created_at.strftime("%d %b %Y, %I:%M %p") if order.created_at else "",
                "updated_at":       order.updated_at.strftime("%d %b %Y, %I:%M %p") if order.updated_at else "",
                "updated_by":       order.updated_by.get_full_name() if order.updated_by else "",
                # items & shipment
                "items":            items,
                "shipment":         shipment_data,
            }
        })
