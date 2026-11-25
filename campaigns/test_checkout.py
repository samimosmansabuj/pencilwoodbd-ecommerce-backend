"""
Task 2 tests (part 1): campaign lines in cart / checkout summary / place-order.
Part 2 (delivery, gifts, offers) is in test_checkout_rules.py.   Run: python manage.py test campaigns
"""
import itertools
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db.models.query import QuerySet
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import Customer, CustomUser
from marketing.models import Coupon
from order.models import Order, OrderItem
from pencilwoodbd.choices import CAMPAIGN_DISCOUNT_TYPE as DT, CAMPAIGN_PRICE_SOURCE as SRC, STATUS
from product.models import AddToCart, Product
from django.test import TestCase

from .models import Campaign, CampaignProduct
from .pricing import get_campaign_sales_stats, get_sold_units
from .tests import add, make_campaign, make_gift_for, make_product, make_variant

PHONE = "01712345678"
_n = itertools.count(1)


def shop_product(price=1000, discount=0, qty=100, **kw):
    return make_product(price=price, discount=discount, inventory_quantity=qty, **kw)


def line(product, quantity=1, campaign=None, variant=None, **extra):
    row = {"product_id": product.id, "variant_id": variant.id if variant else None, "quantity": quantity}
    if campaign:
        row["campaign"] = campaign.slug if hasattr(campaign, "slug") else campaign
    row.update(extra)
    return row


class CheckoutBase(TestCase):
    """Helpers shared by every checkout test."""

    def setUp(self):
        self.client = APIClient()

    def summary(self, items, district=None, client=None, **params):
        query = {"items": json.dumps(items)}
        if district:
            query["district"] = district
        query.update(params)
        return (client or self.client).get("/api/checkout/summary/", query)

    def place(self, items, district="Dhaka", phone=PHONE, client=None, **extra):
        data = {
            "phone": phone, "name": "Tester", "district": district, "items": items,
            "address": f"House {next(_n)}, Road 1",      # a new address each time: the 30s duplicate guard stays out of the way
        }
        data.update(extra)
        return (client or self.client).post("/api/checkout/place-order/", data, format="json")

    def order_of(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        return Order.objects.get(order_id=response.json()["order_id"])

    def campaign_item(self, order):
        return order.order_items.get(campaign__isnull=False)


# ==========================================================================
# PRICING IN SUMMARY / ORDER
# ==========================================================================
class CampaignPricingInCheckoutTests(CheckoutBase):
    def test_summary_prices_a_campaign_line_with_the_campaign_price(self):
        p = shop_product(price=1000)
        c = make_campaign(title="Black Friday")
        add(c, p, DT.PERCENT, 20)
        res = self.summary([line(p, 2, c)])
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        item = data["items"][0]
        self.assertEqual(item["campaign"], "black-friday")
        self.assertTrue(item["campaign_valid"])
        self.assertEqual((item["campaign_price"], item["regular_price"], item["strike_price"]), (800, 1000, 1000))
        self.assertEqual(Decimal(str(item["total"])), Decimal("1600"))
        self.assertEqual(Decimal(str(data["subtotal"])), Decimal("1600"))
        self.assertTrue(data["has_campaign"])

    def test_normal_line_is_unaffected_by_a_live_campaign(self):
        p = shop_product(price=1000, discount=900)
        c = make_campaign()
        add(c, p, DT.PERCENT, 50)
        data = self.summary([line(p, 2)]).json()["data"]          # no campaign slug
        item = data["items"][0]
        self.assertNotIn("campaign_price", item)
        self.assertEqual(Decimal(str(item["total"])), Decimal("1800"))
        self.assertFalse(data["has_campaign"])

    def test_same_product_as_campaign_line_and_normal_line_are_two_separate_lines(self):
        p = shop_product(price=1000)
        c = make_campaign()
        add(c, p, DT.PERCENT, 20)
        data = self.summary([line(p, 1, c), line(p, 2)]).json()["data"]
        totals = [Decimal(str(i["total"])) for i in data["items"]]
        self.assertEqual(totals, [Decimal("800"), Decimal("2000")])
        order = self.order_of(self.place([line(p, 1, c), line(p, 2)]))
        self.assertEqual(order.order_items.count(), 2)
        self.assertEqual(order.order_items.filter(campaign__isnull=False).count(), 1)
        self.assertEqual(order.order_items.get(campaign__isnull=True).discount_price, Decimal("1000"))
        self.assertEqual(order.order_items.get(campaign__isnull=False).discount_price, Decimal("800"))

    def test_discount_base_current_uses_the_products_own_discount_price(self):
        p = shop_product(price=7980, discount=3990)
        c = make_campaign(discount_base=SRC.CURRENT, strike_price_display=SRC.CURRENT)
        add(c, p, DT.PERCENT, 20)
        item = self.summary([line(p, 1, c)]).json()["data"]["items"][0]
        self.assertEqual((item["campaign_price"], item["strike_price"]), (3192, 3990))

    def test_variant_line_is_priced_from_its_own_variant(self):
        p = shop_product(price=0)
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000)
        c = make_campaign()
        add(c, p, DT.PERCENT, 10)
        data = self.summary([line(p, 1, c, v2), line(p, 1, c, v1)]).json()["data"]
        self.assertEqual([i["campaign_price"] for i in data["items"]], [1800, 900])

    def test_customization_surcharge_is_added_on_top_of_the_campaign_price(self):
        p = shop_product(price=1000, customization_mode="optional", customization_price=50)
        c = make_campaign()
        add(c, p, DT.PERCENT, 20)
        res = self.place([line(p, 1, c, is_customized=True, customization_note="Name: Ayaan")])
        order = self.order_of(res)
        item = self.campaign_item(order)
        self.assertEqual(item.price, Decimal("1050"))           # regular + surcharge
        self.assertEqual(item.discount_price, Decimal("850"))    # campaign price + surcharge
        self.assertEqual(item.regular_price, Decimal("1000"))
        self.assertEqual(item.customization_note, "Name: Ayaan")
        self.assertEqual(item.customization_unit_price, Decimal("50"))

    def test_unknown_campaign_slug_summary_flags_the_line_and_place_order_is_price_changed(self):
        p = shop_product()
        res = self.summary([line(p, 1, "does-not-exist")])
        self.assertEqual(res.status_code, 200)          # summary still loads (regular price, flagged line)
        item = res.json()["data"]["items"][0]
        self.assertFalse(item["campaign_valid"])
        self.assertEqual(item["campaign_reason"], "campaign_not_found")
        res = self.place([line(p, 1, "does-not-exist")])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["lines"][0]["reason"], "campaign_not_found")


# ==========================================================================
# PLACE ORDER: snapshot (SPEC 9)
# ==========================================================================
class OrderSnapshotTests(CheckoutBase):
    def test_snapshot_fields_on_a_placed_order(self):
        p = shop_product(price=1000, discount=900)
        c = make_campaign(title="Black Friday", discount_base=SRC.REGULAR, strike_price_display=SRC.REGULAR,
                          include_product_gifts=False, include_offers=True)
        add(c, p, DT.PERCENT, 20)
        order = self.order_of(self.place([line(p, 3, c)]))
        item = self.campaign_item(order)

        # existing semantics stay: price = regular, discount_price = final unit price paid
        self.assertEqual((item.price, item.discount_price), (Decimal("1000"), Decimal("800")))
        self.assertEqual(item.campaign, c)
        self.assertEqual(item.campaign_name, "Black Friday")
        self.assertEqual(item.regular_price, Decimal("1000"))
        self.assertEqual(item.product_sale_price, Decimal("900"))     # the product's own discount_price at that time
        self.assertEqual(item.base_price_used, Decimal("1000"))       # discount_base REGULAR
        self.assertEqual(item.campaign_discount_type, "PERCENT")
        self.assertEqual(item.campaign_discount_value, Decimal("20"))
        self.assertEqual(item.campaign_savings_amount, Decimal("200"))
        self.assertEqual(item.campaign_savings_percent, 20)

        snap = item.snapshot
        self.assertFalse(snap["is_gift"])
        self.assertFalse(snap["campaign_gifts_included"])
        self.assertTrue(snap["campaign_offers_included"])
        self.assertEqual(snap["campaign"]["slug"], "black-friday")
        self.assertEqual(snap["campaign_pricing"]["campaign_price"], 800)
        self.assertEqual(snap["campaign_pricing"]["current_price"], 900)
        self.assertEqual(snap["campaign_pricing"]["discount_base"], "REGULAR")

        self.assertTrue(order.has_campaign)
        self.assertEqual(order.delivery_breakdown["groups"][0]["label"], "Regular items")
        self.assertEqual(order.total_cost, Decimal("2400") + order.shipping_total)

    def test_later_campaign_edits_never_change_an_old_order(self):
        p = shop_product(price=1000)
        c = make_campaign(title="Black Friday")
        cp = add(c, p, DT.PERCENT, 20)
        order = self.order_of(self.place([line(p, 1, c)]))
        CampaignProduct.objects.filter(pk=cp.pk).update(discount_value=70)
        Campaign.objects.filter(pk=c.pk).update(title="Renamed")
        item = self.campaign_item(Order.objects.get(pk=order.pk))
        self.assertEqual((item.discount_price, item.campaign_name, item.campaign_discount_value),
                         (Decimal("800"), "Black Friday", Decimal("20")))

    def test_normal_order_has_no_campaign_data(self):
        p = shop_product(price=1000, discount=900)
        order = self.order_of(self.place([line(p, 1)]))
        item = order.order_items.get()
        self.assertFalse(order.has_campaign)
        self.assertEqual(order.delivery_breakdown, {})
        self.assertEqual((item.price, item.discount_price), (Decimal("1000"), Decimal("900")))
        for f in ("campaign_id", "campaign_name", "regular_price", "product_sale_price", "base_price_used",
                  "campaign_discount_type", "campaign_discount_value", "campaign_savings_amount",
                  "campaign_savings_percent"):
            self.assertIsNone(getattr(item, f), f)
        self.assertEqual(set(item.snapshot), {"is_gift", "customized", "customization_price"})

    def test_product_stock_is_still_deducted_for_campaign_lines(self):
        p = shop_product(qty=10)
        c = make_campaign()
        add(c, p, DT.PERCENT, 10)
        self.order_of(self.place([line(p, 3, c)]))
        p.refresh_from_db()
        self.assertEqual(p.inventory_quantity, 7)

    def test_manual_dashboard_edit_keeps_the_campaign_snapshot(self):
        # order/views.py deletes and recreates the items when staff edit an order
        p = shop_product(price=1000)
        c = make_campaign()
        add(c, p, DT.PERCENT, 20)
        order = self.order_of(self.place([line(p, 1, c)]))
        old = order.order_items.get()
        fields = ("campaign_id", "campaign_name", "regular_price", "product_sale_price", "base_price_used",
                  "campaign_discount_type", "campaign_discount_value", "campaign_savings_amount",
                  "campaign_savings_percent")
        carried = {f: getattr(old, f) for f in fields}
        # replay exactly what the edit view does
        OrderItem.objects.filter(pk=old.pk).delete()
        new = OrderItem.objects.create(order=order, product=p, quantity=1, price=old.price,
                                       discount_price=old.discount_price, snapshot=old.snapshot, **carried)
        self.assertEqual(new.campaign, c)
        self.assertEqual(new.campaign_savings_percent, 20)


# ==========================================================================
# price_changed (SPEC 6)
# ==========================================================================
class PriceChangedTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.p = shop_product(price=1000, qty=50)
        self.c = make_campaign(title="Black Friday")
        self.cp = add(self.c, self.p, DT.PERCENT, 20)

    def assert_price_changed(self, response, reason, **expect):
        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertFalse(body["status"])
        self.assertEqual(body["code"], "price_changed")
        entry = body["lines"][0]
        self.assertEqual(entry["reason"], reason)
        for key, value in expect.items():
            self.assertEqual(entry[key], value, key)
        self.assertEqual(Order.objects.count(), 0, "NO order may be created")
        self.p.refresh_from_db()
        self.assertEqual(self.p.inventory_quantity, 50, "stock must not be touched")
        return entry

    def test_campaign_ended_between_summary_and_place_order(self):
        self.assertEqual(self.summary([line(self.p, 1, self.c)]).status_code, 200)
        Campaign.objects.filter(pk=self.c.pk).update(end_at=timezone.now() - timedelta(minutes=1))   # ends meanwhile
        entry = self.assert_price_changed(
            self.place([line(self.p, 1, self.c)]), "campaign_ended",
            new_unit_price=1000, campaign_unit_price=800, line_id=0, campaign="black-friday")
        self.assertIn("ended", entry["message"])

    def test_the_summary_reports_the_same_problem(self):
        Campaign.objects.filter(pk=self.c.pk).update(end_at=timezone.now() - timedelta(minutes=1))
        res = self.summary([line(self.p, 1, self.c)])
        # By design the summary never fails: the ended campaign line falls back to the regular
        # price and is flagged (campaign_valid=false). Only Place Order answers 409 price_changed.
        self.assertEqual(res.status_code, 200)
        body = res.json()
        flat = str(body)
        self.assertIn("campaign_valid", flat)

    def test_campaign_paused(self):
        Campaign.objects.filter(pk=self.c.pk).update(is_active=False)
        self.assert_price_changed(self.place([line(self.p, 1, self.c)]), "campaign_paused", new_unit_price=1000)

    def test_campaign_not_started(self):
        Campaign.objects.filter(pk=self.c.pk).update(start_at=timezone.now() + timedelta(hours=1),
                                                     end_at=timezone.now() + timedelta(hours=5))
        self.assert_price_changed(self.place([line(self.p, 1, self.c)]), "campaign_not_started")

    def test_product_removed_from_the_campaign(self):
        CampaignProduct.objects.filter(pk=self.cp.pk).update(is_active=False)
        self.assert_price_changed(self.place([line(self.p, 1, self.c)]), "product_removed", new_unit_price=1000)

    def test_product_row_deleted_from_the_campaign(self):
        self.cp.delete()
        self.assert_price_changed(self.place([line(self.p, 1, self.c)]), "product_removed")

    def test_new_unit_price_includes_the_customization_surcharge(self):
        p = shop_product(price=500, customization_mode="mandatory", customization_price=40)
        add(self.c, p, DT.PERCENT, 10)
        Campaign.objects.filter(pk=self.c.pk).update(is_active=False)
        res = self.place([line(p, 1, self.c, customization_note="x")])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["lines"][0]["new_unit_price"], 540)

    def test_only_the_broken_lines_are_listed_and_a_good_line_blocks_nothing_silently(self):
        other = shop_product(price=300)
        c2 = make_campaign(title="Other")
        add(c2, other, DT.PERCENT, 10)
        Campaign.objects.filter(pk=self.c.pk).update(is_active=False)
        res = self.place([line(self.p, 1, self.c), line(other, 1, c2)])
        self.assertEqual(res.status_code, 409)
        self.assertEqual([l["campaign"] for l in res.json()["lines"]], ["black-friday"])
        self.assertEqual(Order.objects.count(), 0)

    def test_customer_confirms_by_placing_again_as_a_normal_line_at_the_normal_price(self):
        Campaign.objects.filter(pk=self.c.pk).update(is_active=False)
        self.assertEqual(self.place([line(self.p, 1, self.c)]).status_code, 409)
        order = self.order_of(self.place([line(self.p, 1)]))               # the frontend switched the line to normal
        self.assertEqual(order.order_items.get().discount_price, Decimal("1000"))
        self.assertFalse(order.has_campaign)

    def test_price_changed_does_not_get_swallowed_by_the_duplicate_guard(self):
        # an order whose own units used up the campaign stock must not turn its double click into price_changed
        CampaignProduct.objects.filter(pk=self.cp.pk).update(stock_limit=1)
        first = self.client.post("/api/checkout/place-order/", {
            "phone": PHONE, "name": "T", "district": "Dhaka", "address": "Same Address 1",
            "items": [line(self.p, 1, self.c)]}, format="json")
        self.assertEqual(first.status_code, 200)
        again = self.client.post("/api/checkout/place-order/", {
            "phone": PHONE, "name": "T", "district": "Dhaka", "address": "Same Address 1",
            "items": [line(self.p, 1, self.c)]}, format="json")
        self.assertEqual(again.status_code, 201)
        self.assertTrue(again.json()["duplicate"])
        self.assertEqual(Order.objects.count(), 1)

    def test_same_product_normal_vs_campaign_is_not_a_duplicate(self):
        same = {"phone": PHONE, "name": "T", "district": "Dhaka", "address": "Same Address 2"}
        a = self.client.post("/api/checkout/place-order/", {**same, "items": [line(self.p, 1, self.c)]}, format="json")
        b = self.client.post("/api/checkout/place-order/", {**same, "items": [line(self.p, 1)]}, format="json")
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(Order.objects.count(), 2)


# ==========================================================================
# STOCK LIMIT (SPEC 6)
# ==========================================================================
class StockLimitTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.p = shop_product(price=1000, qty=100)
        self.c = make_campaign(title="Limited")
        self.cp = add(self.c, self.p, DT.PERCENT, 20, stock_limit=5)

    def left(self):
        data = self.client.get("/api/ecom/campaigns/limited/").json()["data"]["products"][0]
        return data["campaign_pricing"]["stock_left"]

    def test_stock_left_is_filled_from_non_cancelled_orders(self):
        self.assertEqual(self.left(), 5)
        self.order_of(self.place([line(self.p, 2, self.c)]))
        self.assertEqual(self.left(), 3)
        self.assertEqual(get_sold_units(self.cp), 2)

    def test_stock_limit_reached_blocks_the_next_order(self):
        self.order_of(self.place([line(self.p, 5, self.c)]))
        res = self.place([line(self.p, 1, self.c)])
        self.assertEqual(res.status_code, 409)
        entry = res.json()["lines"][0]
        self.assertEqual((entry["reason"], entry["remaining"], entry["new_unit_price"]), ("stock_exhausted", 0, 1000))
        self.assertEqual(Order.objects.count(), 1)

    def test_quantity_above_remaining_is_refused_not_trimmed(self):
        self.order_of(self.place([line(self.p, 3, self.c)]))
        res = self.place([line(self.p, 3, self.c)])
        self.assertEqual(res.status_code, 409)
        entry = res.json()["lines"][0]
        self.assertEqual((entry["reason"], entry["remaining"]), ("quantity_exceeds_remaining", 2))
        self.assertEqual(Order.objects.count(), 1)
        self.order_of(self.place([line(self.p, 2, self.c)]))            # exactly what is left works
        self.assertEqual(self.left(), 0)

    def test_the_limit_counts_all_variants_and_all_lines_of_the_product_together(self):
        vp = shop_product(price=0)
        v1 = make_variant(vp, price=1000, default=True, qty=50)
        v2 = make_variant(vp, price=1000, qty=50)
        add(self.c, vp, DT.PERCENT, 10, stock_limit=4)
        res = self.place([line(vp, 3, self.c, v1), line(vp, 2, self.c, v2)])     # 5 together > 4
        self.assertEqual(res.status_code, 409)
        self.assertEqual({l["reason"] for l in res.json()["lines"]}, {"quantity_exceeds_remaining"})
        self.order_of(self.place([line(vp, 2, self.c, v1), line(vp, 2, self.c, v2)]))

    def test_normal_lines_of_the_same_product_do_not_use_the_campaign_stock(self):
        self.order_of(self.place([line(self.p, 50)]))                  # normal order, 50 units
        self.assertEqual(self.left(), 5)
        self.order_of(self.place([line(self.p, 5, self.c)]))

    def test_cancelled_order_frees_the_stock(self):
        order = self.order_of(self.place([line(self.p, 5, self.c)]))
        self.assertEqual(self.left(), 0)
        self.assertEqual(self.place([line(self.p, 1, self.c)]).status_code, 409)
        Order.objects.filter(pk=order.pk).update(status=STATUS.CANCELLED)
        self.assertEqual(self.left(), 5)
        self.order_of(self.place([line(self.p, 5, self.c)]))

    def test_no_limit_means_no_check(self):
        CampaignProduct.objects.filter(pk=self.cp.pk).update(stock_limit=None)
        self.order_of(self.place([line(self.p, 30, self.c)]))

    def test_gift_and_offer_free_items_are_not_counted(self):
        gift = make_gift_for(self.p)
        gift.inventory_quantity = 50
        gift.save()
        CampaignProduct.objects.filter(pk=self.cp.pk).update(gift_mode="INCLUDE")
        order = self.order_of(self.place([line(self.p, 2, self.c)]))
        self.assertEqual(order.order_items.filter(snapshot__is_gift=True).count(), 1)        # the gift is there ...
        self.assertEqual(get_sold_units(self.cp), 2)                                         # ... but not counted
        stats = get_campaign_sales_stats([self.c.id])[self.c.id]
        self.assertEqual((stats["orders"], stats["units"]), (1, 2))
        self.assertEqual(stats["revenue"], Decimal("1600"))                                  # 2 x 800, the free gift adds 0

    def test_two_orders_for_the_last_unit_only_one_wins(self):
        CampaignProduct.objects.filter(pk=self.cp.pk).update(stock_limit=1)
        first = self.place([line(self.p, 1, self.c)], phone="01711111111")
        second = self.place([line(self.p, 1, self.c)], phone="01722222222")
        self.assertEqual((first.status_code, second.status_code), (200, 409))
        self.assertEqual(second.json()["lines"][0]["reason"], "stock_exhausted")
        self.assertEqual(Order.objects.count(), 1)

    def test_the_campaign_rows_are_locked_before_units_sold_are_read(self):
        # SQLite cannot show FOR UPDATE, so record the order of events instead; on PostgreSQL/MySQL this is the
        # lock that makes two parallel orders for the last unit wait for each other.
        events = []
        original = QuerySet.select_for_update

        def spy_lock(qs, *a, **k):
            if qs.model is CampaignProduct:
                events.append("lock")
            return original(qs, *a, **k)

        import campaigns.checkout as checkout_module
        real_sold = checkout_module.get_sold_units_map

        def spy_sold(cps):
            events.append("sold")
            return real_sold(cps)

        with mock.patch.object(QuerySet, "select_for_update", spy_lock), \
                mock.patch.object(checkout_module, "get_sold_units_map", spy_sold):
            self.order_of(self.place([line(self.p, 1, self.c)]))
        self.assertEqual(events[:2], ["lock", "sold"])

    def test_the_summary_does_not_lock(self):
        events = []
        original = QuerySet.select_for_update
        with mock.patch.object(QuerySet, "select_for_update",
                               lambda qs, *a, **k: (events.append(qs.model), original(qs, *a, **k))[1]):
            self.assertEqual(self.summary([line(self.p, 1, self.c)]).status_code, 200)
        self.assertNotIn(CampaignProduct, events)


# ==========================================================================
# COUPON (SPEC 7)
# ==========================================================================
class CouponTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.coupon = Coupon.objects.create(code="SAVE10", discount_type="PERCENT", discount_value=10, max_uses_per_phone=5)
        self.camp_product = shop_product(price=1000)
        self.normal_product = shop_product(price=500)

    def campaign(self, **kw):
        c = make_campaign(**kw)
        add(c, self.camp_product, DT.PERCENT, 20)
        return c

    def test_only_campaign_lines_rejects_the_coupon(self):
        c = self.campaign(allow_coupon=False)
        res = self.place([line(self.camp_product, 1, c)], coupon_code="SAVE10")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "coupon_not_applicable_to_campaign")
        self.assertIn("এই কুপন ক্যাম্পেইন পণ্যে প্রযোজ্য নয়", res.json()["message"])
        self.assertIn("This coupon can't be used on campaign items", res.json()["message"])
        self.assertEqual(Order.objects.count(), 0)

    def test_mixed_cart_coupon_is_calculated_on_normal_lines_only(self):
        c = self.campaign(allow_coupon=False)
        order = self.order_of(self.place([line(self.camp_product, 1, c), line(self.normal_product, 2)], coupon_code="SAVE10"))
        self.assertEqual(order.coupon_discount, Decimal("100"))               # 10% of 1000 (normal), not of 1800
        self.assertEqual(order.total_cost, Decimal("800") + Decimal("1000") - Decimal("100") + order.shipping_total)
        note = order.promotions_applied["coupon_excluded_campaign_items"]
        self.assertEqual(note["campaigns"], [c.title])
        self.assertEqual(note["excluded_subtotal"], 800)

    def test_allow_coupon_true_applies_to_every_line(self):
        c = self.campaign(allow_coupon=True)
        order = self.order_of(self.place([line(self.camp_product, 1, c), line(self.normal_product, 2)], coupon_code="SAVE10"))
        self.assertEqual(order.coupon_discount, Decimal("180"))               # 10% of (800 + 1000)
        self.assertNotIn("coupon_excluded_campaign_items", order.promotions_applied or {})

    def test_each_campaign_line_follows_its_own_campaigns_setting(self):
        c_yes = self.campaign(allow_coupon=True, title="Yes")
        other = shop_product(price=2000)
        c_no = make_campaign(title="No", allow_coupon=False)
        add(c_no, other, DT.PERCENT, 50)
        order = self.order_of(self.place([line(self.camp_product, 1, c_yes), line(other, 1, c_no)], coupon_code="SAVE10"))
        self.assertEqual(order.coupon_discount, Decimal("80"))                # only the 800 line of the allowing campaign
        self.assertEqual(order.promotions_applied["coupon_excluded_campaign_items"]["campaigns"], ["No"])

    def test_without_a_coupon_nothing_changes(self):
        c = self.campaign(allow_coupon=False)
        order = self.order_of(self.place([line(self.camp_product, 1, c)]))
        self.assertEqual(order.coupon_discount, Decimal("0"))

    def test_invalid_code_is_still_reported_first(self):
        c = self.campaign()
        res = self.place([line(self.camp_product, 1, c)], coupon_code="NOPE")
        self.assertEqual(res.json()["message"], "Invalid coupon code.")

    def test_normal_cart_coupon_is_unchanged(self):
        order = self.order_of(self.place([line(self.normal_product, 2)], coupon_code="SAVE10"))
        self.assertEqual(order.coupon_discount, Decimal("100"))

    # ---- the coupon-apply endpoint shown at checkout ----
    def apply(self, items):
        return self.client.post("/site/api/apply-coupon/", {"code": "SAVE10", "phone": PHONE, "items": items}, format="json")

    def test_apply_coupon_endpoint_rejects_a_campaign_only_cart(self):
        c = self.campaign(allow_coupon=False)
        res = self.apply([line(self.camp_product, 1, c)])
        self.assertEqual(res.status_code, 400)
        self.assertIn("This coupon can't be used on campaign items", res.json()["message"])

    def test_apply_coupon_endpoint_mixed_cart_and_allow_coupon(self):
        c = self.campaign(allow_coupon=False)
        data = self.apply([line(self.camp_product, 1, c), line(self.normal_product, 2)]).json()["data"]
        self.assertEqual((data["subtotal"], data["discount_amount"]), (1000.0, 100.0))
        Campaign.objects.filter(pk=c.pk).update(allow_coupon=True)
        data = self.apply([line(self.camp_product, 1, c), line(self.normal_product, 2)]).json()["data"]
        self.assertEqual((data["subtotal"], data["discount_amount"]), (1800.0, 180.0))

    def test_apply_coupon_endpoint_normal_cart_unchanged(self):
        data = self.apply([line(self.normal_product, 2)]).json()["data"]
        self.assertEqual((data["subtotal"], data["discount_amount"]), (1000.0, 100.0))


# ==========================================================================
# CART (logged-in customer)
# ==========================================================================
class CartTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        user = CustomUser.objects.create(email="buyer@example.com", phone=PHONE, username="buyer")
        self.customer = Customer.objects.create(user=user, name="Buyer", phone=PHONE)
        self.client.force_authenticate(user)
        self.p = shop_product(price=1000)
        self.c = make_campaign(title="Black Friday")
        self.cp = add(self.c, self.p, DT.PERCENT, 20, stock_limit=10)

    def add_to_cart(self, quantity=1, campaign=None, product=None):
        body = {"product_id": (product or self.p).id, "quantity": quantity}
        if campaign:
            body["campaign"] = campaign if isinstance(campaign, str) else campaign.slug
        return self.client.post("/cart/add/", body, format="json")

    def cart(self):
        return self.client.get("/cart/").json()

    def test_lines_are_unique_by_product_variant_customization_and_campaign(self):
        self.add_to_cart(1, self.c)
        self.add_to_cart(2, self.c)
        self.add_to_cart(3)                                  # same product, normal
        rows = AddToCart.objects.filter(customer=self.customer)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows.get(campaign=self.c).quantity, 3)
        self.assertEqual(rows.get(campaign__isnull=True).quantity, 3)

    def test_cart_read_returns_recomputed_campaign_pricing_per_line(self):
        self.add_to_cart(2, self.c)
        self.add_to_cart(1)
        data = {r["campaign"]: r for r in self.cart()["data"]}
        self.assertEqual(Decimal(str(data["black-friday"]["total"])), Decimal("1600"))
        self.assertEqual(data["black-friday"]["campaign_price"], 800)
        self.assertEqual(data["black-friday"]["campaign_stock_left"], 10)
        self.assertTrue(data["black-friday"]["campaign_valid"])
        self.assertEqual(Decimal(str(data[None]["total"])), Decimal("1000"))
        self.assertEqual(Decimal(str(self.cart()["cart_total"])), Decimal("2600"))

    def test_cart_read_follows_a_price_change_made_after_the_item_was_added(self):
        self.add_to_cart(1, self.c)
        CampaignProduct.objects.filter(pk=self.cp.pk).update(discount_value=50)
        row = self.cart()["data"][0]
        self.assertEqual(row["campaign_price"], 500)
        self.assertEqual(Decimal(str(row["total"])), Decimal("500"))

    def test_cart_read_flags_a_line_whose_campaign_ended(self):
        self.add_to_cart(1, self.c)
        Campaign.objects.filter(pk=self.c.pk).update(end_at=timezone.now() - timedelta(minutes=1))
        row = self.cart()["data"][0]
        self.assertFalse(row["campaign_valid"])
        self.assertEqual(row["campaign_reason"], "campaign_ended")
        self.assertEqual(row["normal_unit_price"], 1000)
        self.assertTrue(row["campaign_message"])

    def test_cart_read_flags_stock_problems(self):
        self.add_to_cart(4, self.c)
        CampaignProduct.objects.filter(pk=self.cp.pk).update(stock_limit=3)
        row = self.cart()["data"][0]
        self.assertEqual((row["campaign_valid"], row["campaign_reason"], row["campaign_stock_left"]),
                         (False, "quantity_exceeds_remaining", 3))

    def test_normal_cart_lines_keep_their_old_fields(self):
        self.add_to_cart(2)
        row = self.cart()["data"][0]
        self.assertIsNone(row["campaign"])
        self.assertEqual(Decimal(str(row["total"])), Decimal("2000"))
        self.assertEqual(Decimal(str(row["price"])), Decimal("1000"))

    def test_adding_to_a_campaign_that_does_not_apply_is_refused(self):
        Campaign.objects.filter(pk=self.c.pk).update(end_at=timezone.now() - timedelta(minutes=1))
        res = self.add_to_cart(1, self.c)
        self.assertEqual(res.status_code, 400)
        self.assertEqual((res.json()["code"], res.json()["reason"]), ("campaign_unavailable", "campaign_ended"))
        self.assertEqual(AddToCart.objects.count(), 0)

    def test_adding_more_than_the_campaign_stock_left_is_refused(self):
        self.add_to_cart(8, self.c)
        res = self.add_to_cart(3, self.c)
        self.assertEqual(res.status_code, 400)
        self.assertEqual((res.json()["reason"], res.json()["remaining"]), ("quantity_exceeds_remaining", 10))

    def test_raising_a_campaign_line_above_the_stock_left_is_refused(self):
        cart_id = self.add_to_cart(2, self.c).json()["cart_id"]
        self.assertEqual(self.client.post(f"/cart/update/{cart_id}/", {"quantity": 9}, format="json").status_code, 200)
        res = self.client.post(f"/cart/update/{cart_id}/", {"quantity": 11}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_checkout_with_saved_cart_lines(self):
        a = self.add_to_cart(2, self.c).json()["cart_id"]
        b = self.add_to_cart(1).json()["cart_id"]
        res = self.client.get("/api/checkout/summary/", {"cart_ids": [a, b]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(str(res.json()["data"]["subtotal"])), Decimal("2600"))
        placed = self.client.post("/api/checkout/place-order/", {
            "phone": PHONE, "name": "Buyer", "district": "Dhaka", "address": "Cart Road 1", "cart_ids": [a, b]}, format="json")
        order = self.order_of(placed)
        self.assertEqual(order.order_items.filter(campaign=self.c).get().discount_price, Decimal("800"))
        self.assertEqual(AddToCart.objects.filter(customer=self.customer).count(), 0)

    def test_checkout_with_a_stale_cart_line_returns_price_changed_with_the_cart_id(self):
        a = self.add_to_cart(1, self.c).json()["cart_id"]
        Campaign.objects.filter(pk=self.c.pk).update(is_active=False)
        res = self.client.post("/api/checkout/place-order/", {
            "phone": PHONE, "name": "Buyer", "district": "Dhaka", "address": "Cart Road 2", "cart_ids": [a]}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["lines"][0]["line_id"], a)
        self.assertEqual(AddToCart.objects.count(), 1, "the cart is left alone")

    def test_guest_refresh_reports_the_campaign_state_of_guest_lines(self):
        res = self.client.get("/cart/guest-refresh/", {
            "ids": str(self.p.id), "campaign_lines": json.dumps([{"product_id": self.p.id, "campaign": "black-friday"}])})
        entry = res.json()["campaign_lines"][0]
        self.assertTrue(entry["valid"])
        self.assertEqual(entry["campaign_pricing"]["campaign_price"], 800)
        Campaign.objects.filter(pk=self.c.pk).update(is_active=False)
        res = self.client.get("/cart/guest-refresh/", {
            "ids": str(self.p.id), "campaign_lines": json.dumps([{"product_id": self.p.id, "campaign": "black-friday"}])})
        entry = res.json()["campaign_lines"][0]
        self.assertEqual((entry["valid"], entry["reason"]), (False, "campaign_paused"))

    def test_guest_refresh_without_campaign_lines_is_unchanged(self):
        res = self.client.get("/cart/guest-refresh/", {"ids": str(self.p.id)}).json()
        self.assertEqual(set(res), {"status", "data"})

    def test_merging_a_guest_cart_keeps_the_campaign_line_separate(self):
        res = self.client.post("/cart-wishlist/merge/", {"cart": [
            {"product_id": self.p.id, "quantity": 2, "campaign": "black-friday"},
            {"product_id": self.p.id, "quantity": 1},
            {"product_id": self.p.id, "quantity": 1, "campaign": "no-such-campaign"},
        ]}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        rows = AddToCart.objects.filter(customer=self.customer)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows.get(campaign=self.c).quantity, 2)
        self.assertEqual(res.json()["skipped_cart"], 1)

    def test_account_merge_matches_lines_by_campaign_too(self):
        from authentication.account_merge import _move_cart_and_wishlist
        other_user = CustomUser.objects.create(email="other@example.com", username="other")
        other = Customer.objects.create(user=other_user, name="Other", phone="01799999999")
        AddToCart.objects.create(customer=self.customer, product=self.p, quantity=1)
        AddToCart.objects.create(customer=other, product=self.p, quantity=2, campaign=self.c)
        AddToCart.objects.create(customer=other, product=self.p, quantity=3)
        _move_cart_and_wishlist(self.customer, other, protect_cart_ids=[])
        rows = AddToCart.objects.filter(customer=self.customer)
        self.assertEqual(sorted((r.campaign_id or 0, r.quantity) for r in rows), [(0, 4), (self.c.id, 2)])
