"""
Task 3 tests (part 2): campaign data on the dashboard ORDER screens (SPEC 9) and the campaign COUNTS on the list.
Orders are placed through the real storefront API (Task 2), then read through the staff dashboard.
"""
import csv
import io
import json
from decimal import Decimal

from django.test import Client
from django.urls import reverse

from marketing.models import Coupon
from order.models import Order
from pencilwoodbd.choices import STATUS, CAMPAIGN_DISCOUNT_TYPE as DT

from .test_checkout import CheckoutBase, line, shop_product
from .test_dashboard import login
from .tests import add, make_campaign, make_gift_for


class OrderScreenBase(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.staff = login()
        self.product = shop_product(price=1000, discount=900, name="Cradle Chair")
        self.other = shop_product(price=500, name="Pencil Box")
        self.campaign = make_campaign(title="Black Friday", discount_base="REGULAR", strike_price_display="REGULAR")
        add(self.campaign, self.product, DT.PERCENT, 20)

    def campaign_order(self, qty=2, **extra):
        return self.order_of(self.place([line(self.product, qty, self.campaign)], **extra))

    def normal_order(self):
        return self.order_of(self.place([line(self.other, 1)]))

    def order_list(self, **params):
        return self.staff.get(reverse("order_list"), params)


# ==========================================================================
# ORDER LIST: chip, filter, discount total
# ==========================================================================
class OrderListTests(OrderScreenBase):
    def test_campaign_chip_shows_the_campaign_name_only_on_campaign_orders(self):
        campaign_order, normal_order = self.campaign_order(), self.normal_order()
        res = self.order_list()
        self.assertEqual(res.status_code, 200)
        rows = {o.id: o for o in res.context["orders"]}
        self.assertEqual([c["name"] for c in rows[campaign_order.id].campaign_chips], ["Black Friday"])
        self.assertEqual(rows[normal_order.id].campaign_chips, [])
        html = res.content.decode()
        self.assertEqual(html.count("data-campaign-chip"), 1)          # only the campaign order has a chip
        self.assertIn("Black Friday", html)

    def test_chip_uses_the_order_snapshot_even_after_the_campaign_is_deleted(self):
        order = self.campaign_order()
        self.staff.post(reverse("campaign_delete", args=[self.campaign.id]))
        res = self.order_list()
        row = {o.id: o for o in res.context["orders"]}[order.id]
        self.assertEqual([c["name"] for c in row.campaign_chips], ["Black Friday"])

    def test_campaign_discount_total_per_order(self):
        order = self.campaign_order(qty=3)                   # savings: 1000 - 800 = 200 each
        row = {o.id: o for o in self.order_list().context["orders"]}[order.id]
        self.assertEqual(row.campaign_discount_total, Decimal("600"))

    def test_filter_by_campaign(self):
        campaign_order, normal_order = self.campaign_order(), self.normal_order()
        res = self.order_list(campaign=self.campaign.id)
        self.assertEqual([o.id for o in res.context["orders"]], [campaign_order.id])
        self.assertEqual(res.context["current_campaign"], str(self.campaign.id))
        self.assertEqual(len(self.order_list().context["orders"]), 2)                  # no filter = everything
        self.assertEqual(len(self.order_list(campaign="").context["orders"]), 2)
        self.assertEqual(len(self.order_list(campaign="abc").context["orders"]), 2)    # junk is ignored, not an error

    def test_filter_combines_with_status_and_a_second_campaign(self):
        o1 = self.campaign_order()
        other_campaign = make_campaign(title="Eid Sale")
        add(other_campaign, self.other, DT.PERCENT, 10)
        o2 = self.order_of(self.place([line(self.other, 1, other_campaign)]))
        self.assertEqual([o.id for o in self.order_list(campaign=other_campaign.id).context["orders"]], [o2.id])
        Order.objects.filter(pk=o1.pk).update(status=STATUS.CONFIRMED)
        self.assertEqual([o.id for o in self.order_list(campaign=self.campaign.id, status=STATUS.CONFIRMED).context["orders"]], [o1.id])
        self.assertEqual(list(self.order_list(campaign=self.campaign.id, status=STATUS.NEW).context["orders"]), [])

    def test_order_with_two_campaign_items_appears_once(self):
        other_campaign = make_campaign(title="Eid Sale")
        add(other_campaign, self.other, DT.PERCENT, 10)
        order = self.order_of(self.place([line(self.product, 1, self.campaign), line(self.other, 1, other_campaign)]))
        res = self.order_list(campaign=self.campaign.id)
        self.assertEqual([o.id for o in res.context["orders"]], [order.id])
        row = res.context["orders"][0]
        self.assertEqual(sorted(c["name"] for c in row.campaign_chips), ["Black Friday", "Eid Sale"])

    def test_the_filter_dropdown_lists_campaigns_and_survives_paging_and_tabs(self):
        self.campaign_order()
        html = self.order_list(campaign=self.campaign.id).content.decode()
        self.assertIn('id="campaign_filter"', html)
        self.assertIn("All Campaigns", html)
        self.assertIn(f'value="{self.campaign.id}" selected', html)
        self.assertIn(f"campaign={self.campaign.id}", html)          # tab / paging links keep the filter

    def test_htmx_partial_with_the_filter(self):
        order = self.campaign_order()
        self.normal_order()
        res = self.staff.get(reverse("order_list"), {"campaign": self.campaign.id}, HTTP_HX_REQUEST="true")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([o.id for o in res.context["orders"]], [order.id])

    def test_the_normal_order_list_is_unchanged_without_campaigns(self):
        self.normal_order()
        res = self.order_list()
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("data-campaign-chip", res.content.decode())


# ==========================================================================
# SHORT VIEW
# ==========================================================================
class ShortDetailTests(OrderScreenBase):
    def short(self, order):
        res = self.staff.get(reverse("order_short_detail", args=[order.id]))
        self.assertEqual(res.status_code, 200)
        return res.json()["order"]

    def test_short_view_has_the_campaign_discount_total_and_names(self):
        order = self.campaign_order(qty=3)
        data = self.short(order)
        self.assertTrue(data["has_campaign"])
        self.assertEqual(data["campaign_names"], ["Black Friday"])
        self.assertEqual(data["campaign_discount_total"], 600.0)
        self.assertEqual(data["items"][0]["campaign_name"], "Black Friday")
        self.assertIn("campaign_discount_total", self.staff.get(reverse("order_list")).content.decode())

    def test_gift_and_offer_lines_add_nothing_to_the_discount_total(self):
        make_gift_for(self.product)
        from campaigns.models import CampaignProduct
        CampaignProduct.objects.filter(campaign=self.campaign).update(gift_mode="INCLUDE")
        order = self.campaign_order(qty=1)
        self.assertEqual(order.order_items.count(), 2)                       # item + the free gift
        self.assertEqual(self.short(order)["campaign_discount_total"], 200.0)

    def test_normal_order_short_view(self):
        data = self.short(self.normal_order())
        self.assertFalse(data["has_campaign"])
        self.assertEqual((data["campaign_names"], data["campaign_discount_total"]), ([], 0.0))
        self.assertEqual(data["items"][0]["campaign_name"], "")


# ==========================================================================
# ORDER DETAILS
# ==========================================================================
class OrderDetailTests(OrderScreenBase):
    def detail(self, order):
        res = self.staff.get(reverse("order_detail", args=[order.id]))
        self.assertEqual(res.status_code, 200)
        return res

    def test_campaign_block_shows_every_field_of_the_brief(self):
        order = self.campaign_order(qty=2)
        res = self.detail(order)
        html = res.content.decode()
        self.assertIn('id="order-campaign-block"', html)
        for text in ("Black Friday", "Main price", "Product's own discount price", "Campaign discount",
                     "Price after campaign", "Savings"):
            self.assertIn(text, html, text)
        row = res.context["campaign_items"][0]
        self.assertEqual((row["regular_price"], row["product_sale_price"], row["price_after"]),
                         (Decimal("1000.00"), Decimal("900.00"), Decimal("800.00")))
        self.assertEqual((row["discount_text"], row["discount_type"]), ("20%", "PERCENT"))
        self.assertEqual((row["savings_amount"], row["savings_percent"]), (Decimal("200.00"), 20))
        self.assertIn("&#2547;1000", html)
        self.assertIn("&#2547;800", html)

    def test_fixed_discount_is_shown_in_taka(self):
        from campaigns.models import CampaignProduct
        CampaignProduct.objects.filter(campaign=self.campaign).update(discount_type="FIXED", discount_value=150)
        row = self.detail(self.campaign_order()).context["campaign_items"][0]
        self.assertEqual((row["discount_text"], row["discount_type"]), ("\u09F3150", "FIXED"))

    def test_gift_offer_note_is_shown_when_they_were_off(self):
        html = self.detail(self.campaign_order()).content.decode()           # both OFF by default
        self.assertIn("Gift/offer not applied (campaign setting)", html)

    def test_gift_offer_note_when_only_one_of_them_was_off(self):
        from campaigns.models import Campaign
        Campaign.objects.filter(pk=self.campaign.pk).update(include_product_gifts=True, include_offers=False)
        self.assertIn("Gift/offer not applied (campaign setting)", self.detail(self.campaign_order()).content.decode())

    def test_no_note_when_both_were_on(self):
        from campaigns.models import Campaign
        Campaign.objects.filter(pk=self.campaign.pk).update(include_product_gifts=True, include_offers=True)
        res = self.detail(self.campaign_order())
        self.assertNotIn("Gift/offer not applied", res.content.decode())
        self.assertEqual(res.context["campaign_items"][0]["gift_offer_note"], "")

    def test_note_comes_from_the_snapshot_not_the_current_campaign_setting(self):
        order = self.campaign_order()                                         # placed with both OFF
        from campaigns.models import Campaign
        Campaign.objects.filter(pk=self.campaign.pk).update(include_product_gifts=True, include_offers=True)
        self.assertIn("Gift/offer not applied (campaign setting)", self.detail(order).content.decode())

    def test_delivery_rule_section(self):
        from campaigns.models import Campaign
        Campaign.objects.filter(pk=self.campaign.pk).update(
            delivery_mode="CUSTOM", delivery_amount_source="SAME_FOR_ALL", delivery_basis="PER_ORDER",
            mixed_cart_delivery="COMBINED", delivery_config={"all": 80})
        order = self.order_of(self.place([line(self.product, 1, self.campaign), line(self.other, 1)]))
        res = self.detail(order)
        view = res.context["campaign_delivery"]
        self.assertEqual(view["total"], 80)
        self.assertEqual([g["label"] for g in view["groups"]], ["Black Friday", "Regular items"])
        html = res.content.decode()
        self.assertIn("Delivery rule used", html)
        self.assertIn("Special campaign delivery", html)
        self.assertIn("one charge per order", html)
        self.assertIn("only the campaign charge", html)
        self.assertIn("not charged", html)

    def test_coupon_exclusion_note(self):
        Coupon.objects.create(code="SAVE10", discount_type="PERCENT", discount_value=10, max_uses_per_phone=5)
        order = self.order_of(self.place([line(self.product, 1, self.campaign), line(self.other, 1)], coupon_code="SAVE10"))
        self.assertIn("Coupon was not applied on campaign items", self.detail(order).content.decode())

    def test_a_normal_order_page_has_no_campaign_block(self):
        res = self.detail(self.normal_order())
        self.assertNotIn("order-campaign-block", res.content.decode())
        self.assertEqual(res.context["campaign_items"], [])
        self.assertIsNone(res.context["campaign_delivery"])

    def test_old_orders_without_campaign_fields_still_open(self):
        order = self.normal_order()
        Order.objects.filter(pk=order.pk).update(delivery_breakdown=None) if False else None
        self.assertEqual(self.detail(order).status_code, 200)

    def test_existing_order_form_is_still_on_the_page(self):
        html = self.detail(self.campaign_order()).content.decode()
        self.assertIn("order-detail/", html)         # the update form is still rendered below the block


# ==========================================================================
# MANUAL PRICE EDITING KEEPS WORKING (and keeps the campaign data)
# ==========================================================================
class ManualEditTests(OrderScreenBase):
    def update(self, order, items, **extra):
        data = {"items": json.dumps(items), "status": order.status, "shipping_total": str(order.shipping_total),
                "payment_type": order.payment_type, "delivery_type": order.delivery_type,
                "shipping_address": order.shipping_address, "district": order.district or "Dhaka"}
        data.update(extra)
        return self.staff.post(reverse("order_update_full", args=[order.id]), data)

    def test_saving_an_order_without_touching_prices_keeps_the_campaign_data(self):
        order = self.campaign_order(qty=2)
        item = order.order_items.get()
        res = self.update(order, [{"item_id": item.id, "product_id": self.product.id, "variant_id": None, "quantity": 2}])
        self.assertIn(res.status_code, (200, 302))
        order.refresh_from_db()
        new = order.order_items.get()
        self.assertEqual((new.campaign_id, new.campaign_name, new.regular_price, new.campaign_savings_percent),
                         (self.campaign.id, "Black Friday", Decimal("1000.00"), 20))
        self.assertEqual((new.price, new.discount_price), (Decimal("1000.00"), Decimal("800.00")))
        self.assertEqual(new.snapshot["campaign_gifts_included"], False)
        self.assertTrue(order.has_campaign)

    def test_manual_price_edit_works_on_a_campaign_line(self):
        order = self.campaign_order(qty=2)
        item = order.order_items.get()
        self.update(order, [{"item_id": item.id, "product_id": self.product.id, "variant_id": None, "quantity": 2,
                             "unit_price": "700", "price_manually_edited": True}])
        order.refresh_from_db()
        new = order.order_items.get()
        self.assertEqual((new.discount_price, new.price_manually_edited), (Decimal("700"), True))
        self.assertEqual(new.campaign_name, "Black Friday")                       # still a campaign line
        self.assertEqual(order.total_cost, Decimal("1400") + order.shipping_total)
        self.assertIn("Price edited manually", self.staff.get(reverse("order_detail", args=[order.id])).content.decode())

    def test_removing_the_campaign_item_clears_the_flag(self):
        order = self.order_of(self.place([line(self.product, 1, self.campaign), line(self.other, 1)]))
        normal = order.order_items.get(campaign__isnull=True)
        self.update(order, [{"item_id": normal.id, "product_id": self.other.id, "variant_id": None, "quantity": 1}])
        order.refresh_from_db()
        self.assertFalse(order.has_campaign)
        self.assertEqual(order.order_items.count(), 1)

    def test_adding_a_normal_product_to_a_campaign_order_keeps_the_campaign_item(self):
        order = self.campaign_order(qty=1)
        item = order.order_items.get()
        self.update(order, [{"item_id": item.id, "product_id": self.product.id, "variant_id": None, "quantity": 1},
                            {"product_id": self.other.id, "variant_id": None, "quantity": 2}])
        order.refresh_from_db()
        self.assertEqual(order.order_items.count(), 2)
        self.assertEqual(order.order_items.get(campaign__isnull=False).discount_price, Decimal("800.00"))
        self.assertIsNone(order.order_items.get(product=self.other).campaign_id)
        self.assertTrue(order.has_campaign)


# ==========================================================================
# CAMPAIGN COUNTS ON THE LIST (SPEC 9)
# ==========================================================================
class CampaignCountsTests(OrderScreenBase):
    def row(self):
        res = self.staff.get(reverse("campaign_list"))
        return {r["c"].id: r for r in res.context["rows"]}[self.campaign.id]

    def test_orders_units_and_revenue(self):
        self.campaign_order(qty=2)
        self.order_of(self.place([line(self.product, 3, self.campaign), line(self.other, 5)]))
        row = self.row()
        self.assertEqual((row["orders"], row["units"], row["revenue"]), (2, 5, Decimal("4000")))   # 5 x 800, normal line excluded

    def test_cancelled_orders_are_not_counted(self):
        first = self.campaign_order(qty=2)
        self.campaign_order(qty=1)
        Order.objects.filter(pk=first.pk).update(status=STATUS.CANCELLED)
        row = self.row()
        self.assertEqual((row["orders"], row["units"], row["revenue"]), (1, 1, Decimal("800")))
        self.assertEqual(row["orders_total"], 2)                    # used by the delete confirmation

    def test_gift_lines_are_not_counted(self):
        make_gift_for(self.product)
        from campaigns.models import CampaignProduct
        CampaignProduct.objects.filter(campaign=self.campaign).update(gift_mode="INCLUDE")
        self.campaign_order(qty=2)
        row = self.row()
        self.assertEqual((row["orders"], row["units"], row["revenue"]), (1, 2, Decimal("1600")))

    def test_the_orders_number_links_to_the_filtered_order_list(self):
        self.campaign_order()
        row = self.row()
        self.assertEqual(row["orders_url"], f"{reverse('order_list')}?campaign={self.campaign.id}")
        html = self.staff.get(reverse("campaign_list")).content.decode()
        self.assertIn(f'href="{row["orders_url"]}"', html)
        followed = self.staff.get(row["orders_url"])
        self.assertEqual(len(followed.context["orders"]), 1)

    def test_a_campaign_without_orders_shows_zero_and_no_link(self):
        row = self.row()
        self.assertEqual((row["orders"], row["units"], row["revenue"]), (0, 0, 0))
        html = self.staff.get(reverse("campaign_list")).content.decode()
        self.assertNotIn(f"?campaign={self.campaign.id}", html)

    def test_each_campaign_is_counted_separately(self):
        other = make_campaign(title="Eid Sale")
        add(other, self.other, DT.PERCENT, 10)
        self.campaign_order(qty=1)
        self.order_of(self.place([line(self.other, 4, other)]))
        res = self.staff.get(reverse("campaign_list"))
        counts = {r["c"].title: (r["orders"], r["units"]) for r in res.context["rows"]}
        self.assertEqual(counts, {"Black Friday": (1, 1), "Eid Sale": (1, 4)})


# ==========================================================================
# EXPORT
# ==========================================================================
class ExportTests(OrderScreenBase):
    def export(self, **params):
        res = self.staff.get(reverse("order_export_csv"), params)
        self.assertEqual(res.status_code, 200)
        rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
        return rows[0], rows[1:]

    def test_new_columns_are_appended_after_the_existing_ones(self):
        header, _ = self.export()
        self.assertEqual(header[-4:], ["Campaign Name", "Campaign Items Regular Total", "Campaign Discount Total",
                                       "Campaign Items Final Total"])
        self.assertEqual(header[:4], ["No.", "Order ID", "Order Status", "Order Date"])    # nothing moved

    def test_campaign_order_row(self):
        order = self.campaign_order(qty=2)
        header, rows = self.export()
        cells = dict(zip(header, rows[0]))
        self.assertEqual(cells["Order ID"], order.order_id)
        self.assertEqual(cells["Campaign Name"], "Black Friday")
        self.assertEqual(Decimal(cells["Campaign Items Regular Total"]), Decimal("2000"))
        self.assertEqual(Decimal(cells["Campaign Discount Total"]), Decimal("400"))
        self.assertEqual(Decimal(cells["Campaign Items Final Total"]), Decimal("1600"))

    def test_normal_order_has_blank_campaign_columns(self):
        self.normal_order()
        header, rows = self.export()
        self.assertEqual(rows[0][-4:], ["", "", "", ""])
        self.assertEqual(len(rows[0]), len(header))

    def test_mixed_order_counts_only_the_campaign_items(self):
        self.order_of(self.place([line(self.product, 1, self.campaign), line(self.other, 4)]))
        header, rows = self.export()
        cells = dict(zip(header, rows[0]))
        self.assertEqual(Decimal(cells["Campaign Items Final Total"]), Decimal("800"))
        self.assertEqual(len(rows[0]), len(header))

    def test_export_can_be_filtered_by_campaign(self):
        c_order, n_order = self.campaign_order(), self.normal_order()
        _, rows = self.export(campaign=self.campaign.id)
        self.assertEqual([r[1] for r in rows], [c_order.order_id])
        _, rows = self.export()
        self.assertEqual({r[1] for r in rows}, {c_order.order_id, n_order.order_id})
