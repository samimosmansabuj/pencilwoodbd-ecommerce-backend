"""
Task 2 tests (part 2): campaign delivery rules (SPEC 8) and gifts / offers switches (SPEC 12).
Run: python manage.py test campaigns
"""
from decimal import Decimal

from offers.models import Offer, OfferGift, OfferTier
from order.models import Order
from pencilwoodbd.choices import (
    CAMPAIGN_DISCOUNT_TYPE as DT,
    CAMPAIGN_SWITCH_MODE as SW,
    OFFER_GIFT_MODE,
)
from product.models import ProductDeliveryCharge
from site_app.models import SiteDeliveryChargeConfig

from .models import Campaign, CampaignProduct
from .pricing import get_campaign_sales_stats
from .tests import add, make_campaign, make_gift_for, make_variant
from .test_checkout import CheckoutBase, line, shop_product


def d(value):
    return Decimal(str(value))


# ==========================================================================
# DELIVERY (SPEC 8)
# ==========================================================================
class CampaignDeliveryTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        SiteDeliveryChargeConfig.objects.update_or_create(pk=1, defaults={"area_and_charge": {"Dhaka": 60, "all": 120}})
        self.p1 = shop_product(price=1000)
        self.p2 = shop_product(price=2000)
        self.normal = shop_product(price=500)

    def camp(self, products=None, **kw):
        defaults = dict(delivery_mode="CUSTOM", delivery_amount_source="SAME_FOR_ALL", delivery_config={"all": 80},
                        delivery_basis="PER_ORDER", mixed_cart_delivery="COMBINED")
        defaults.update(kw)
        c = make_campaign(**defaults)
        for p in (products if products is not None else [self.p1, self.p2]):
            add(c, p, DT.PERCENT, 10)
        return c

    def delivery(self, items, district="Dhaka"):
        res = self.summary(items, district=district)
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()["data"]
        return d(data["delivery_charge"]), data["delivery_breakdown"], data

    # ---- amount source x basis ----
    def test_same_for_all_per_order_is_one_charge_for_all_campaign_products(self):
        c = self.camp()
        total, bd, _ = self.delivery([line(self.p1, 1, c), line(self.p2, 3, c)])
        self.assertEqual(total, 80)
        group = bd["groups"][0]
        self.assertEqual((group["type"], group["label"], group["amount"]), ("campaign", c.title, 80))
        self.assertEqual(group["rule"]["basis"], "PER_ORDER")
        self.assertEqual(len(group["products"]), 2)

    def test_same_for_all_per_product_sums_distinct_products_once(self):
        c = self.camp(delivery_basis="PER_PRODUCT")
        self.assertEqual(self.delivery([line(self.p1, 1, c), line(self.p2, 1, c)])[0], 160)
        vp = shop_product(price=0)
        v1, v2 = make_variant(vp, price=1000, default=True), make_variant(vp, price=1000)
        add(c, vp, DT.PERCENT, 10)
        total, _, _ = self.delivery([line(vp, 1, c, v1), line(vp, 2, c, v2)])          # one product, two lines
        self.assertEqual(total, 80)

    def test_product_wise_with_fallback_to_the_campaign_config(self):
        c = self.camp(delivery_amount_source="PRODUCT_WISE", delivery_basis="PER_ORDER")
        CampaignProduct.objects.filter(campaign=c, product=self.p1).update(delivery_config={"all": 50})
        # p2 has no config of its own -> campaign config 80
        self.assertEqual(self.delivery([line(self.p1, 1, c), line(self.p2, 1, c)])[0], 80)          # highest
        self.assertEqual(self.delivery([line(self.p1, 1, c)])[0], 50)
        Campaign.objects.filter(pk=c.pk).update(delivery_basis="PER_PRODUCT")
        self.assertEqual(self.delivery([line(self.p1, 1, c), line(self.p2, 1, c)])[0], 130)          # 50 + 80

    def test_same_for_all_ignores_the_product_rows_config(self):
        c = self.camp(delivery_amount_source="SAME_FOR_ALL")
        CampaignProduct.objects.filter(campaign=c, product=self.p1).update(delivery_config={"all": 999})
        self.assertEqual(self.delivery([line(self.p1, 1, c)])[0], 80)

    def test_district_rule_with_all_key(self):
        c = self.camp(delivery_config={"Dhaka": 60, "all": 100})
        self.assertEqual(self.delivery([line(self.p1, 1, c)], "Dhaka")[0], 60)
        self.assertEqual(self.delivery([line(self.p1, 1, c)], "Sylhet")[0], 100)

    def test_district_missing_from_campaign_config_falls_back_like_the_existing_resolver(self):
        c = self.camp(delivery_config={"Dhaka": 60})
        self.assertEqual(self.delivery([line(self.p1, 1, c)], "Sylhet")[0], 120)       # global "all"

    # ---- mixed cart ----
    def test_combined_whole_order_pays_only_the_campaign_charge(self):
        c = self.camp(mixed_cart_delivery="COMBINED")
        total, bd, _ = self.delivery([line(self.p1, 1, c), line(self.normal, 2)])
        self.assertEqual(total, 80)
        normal = bd["groups"][1]
        self.assertEqual((normal["label"], normal["amount"], normal["waived"], normal["normal_amount"]),
                         ("Regular items", 0, True, 60))
        self.assertTrue(bd["normal_items_waived"])

    def test_separate_adds_the_normal_charge(self):
        c = self.camp(mixed_cart_delivery="SEPARATE")
        total, bd, _ = self.delivery([line(self.p1, 1, c), line(self.normal, 1)], "Dhaka")
        self.assertEqual(total, 140)
        self.assertEqual([g["amount"] for g in bd["groups"]], [80, 60])
        self.assertEqual(self.delivery([line(self.p1, 1, c), line(self.normal, 1)], "Sylhet")[0], 200)

    def test_separate_keeps_per_product_overrides_of_normal_items(self):
        ProductDeliveryCharge.objects.create(product=self.normal, area_and_charge={"all": 200})
        c = self.camp(mixed_cart_delivery="SEPARATE")
        self.assertEqual(self.delivery([line(self.p1, 1, c), line(self.normal, 1)])[0], 280)

    def test_campaign_items_only_cart_has_no_regular_group(self):
        c = self.camp()
        _, bd, _ = self.delivery([line(self.p1, 1, c)])
        self.assertEqual([g["type"] for g in bd["groups"]], ["campaign"])

    # ---- campaign with NORMAL delivery ----
    def test_normal_delivery_mode_follows_the_normal_rules_exactly(self):
        c = self.camp(delivery_mode="NORMAL", delivery_config={})
        total, bd, _ = self.delivery([line(self.p1, 1, c), line(self.p2, 1, c)], "Dhaka")
        self.assertEqual(total, 120)                                  # two distinct products x 60, as today
        self.assertEqual([g["type"] for g in bd["groups"]], ["normal"])

    def test_normal_mode_campaign_item_and_normal_line_of_the_same_product_are_charged_once(self):
        c = self.camp(delivery_mode="NORMAL", delivery_config={})
        self.assertEqual(self.delivery([line(self.p1, 1, c), line(self.p1, 1)])[0], 60)

    def test_normal_mode_campaign_never_waives_a_custom_campaigns_normal_items(self):
        normal_mode = self.camp(products=[self.p2], delivery_mode="NORMAL", delivery_config={}, title="Normal mode")
        custom = self.camp(products=[self.p1], mixed_cart_delivery="SEPARATE", title="Custom")
        total, bd, _ = self.delivery([line(self.p1, 1, custom), line(self.p2, 1, normal_mode)])
        self.assertEqual(total, 80 + 60)

    # ---- several campaigns ----
    def test_two_campaigns_are_charged_by_their_own_rule_and_added(self):
        a = self.camp(products=[self.p1], title="A", delivery_config={"all": 80}, mixed_cart_delivery="SEPARATE")
        pb1, pb2 = shop_product(price=300), shop_product(price=400)
        b = self.camp(products=[pb1, pb2], title="B", delivery_config={"all": 30}, delivery_basis="PER_PRODUCT",
                      mixed_cart_delivery="SEPARATE")
        total, bd, _ = self.delivery([line(self.p1, 1, a), line(pb1, 1, b), line(pb2, 1, b)])
        self.assertEqual(total, 80 + 60)
        self.assertEqual([(g["label"], g["amount"]) for g in bd["groups"]], [("A", 80), ("B", 60)])
        total, bd, _ = self.delivery([line(self.p1, 1, a), line(pb1, 1, b), line(self.normal, 1)])
        self.assertEqual(total, 80 + 30 + 60)                          # normal items charged: both SEPARATE

    def test_any_combined_campaign_waives_the_normal_items(self):
        a = self.camp(products=[self.p1], title="A", delivery_config={"all": 80}, mixed_cart_delivery="COMBINED")
        pb = shop_product(price=300)
        b = self.camp(products=[pb], title="B", delivery_config={"all": 30}, mixed_cart_delivery="SEPARATE")
        total, bd, _ = self.delivery([line(self.p1, 1, a), line(pb, 1, b), line(self.normal, 1)])
        self.assertEqual(total, 110)
        self.assertTrue(bd["normal_items_waived"])

    # ---- before a district is chosen ----
    def test_without_a_district_the_lowest_charge_is_shown_like_the_existing_summary(self):
        c = self.camp(delivery_config={"Dhaka": 60, "all": 100})
        data = self.summary([line(self.p1, 1, c)]).json()["data"]
        self.assertEqual(d(data["delivery_charge"]), 60)
        info = data["delivery_info"]
        self.assertEqual((info["district_selected"], info["min"], info["max"], info["varies"]), (False, 60.0, 100.0, True))
        self.assertFalse(data["delivery_breakdown"]["district_selected"])

    # ---- stored on the order ----
    def test_the_order_stores_the_charge_and_the_breakdown(self):
        c = self.camp(delivery_config={"Dhaka": 60, "all": 100}, mixed_cart_delivery="SEPARATE")
        order = self.order_of(self.place([line(self.p1, 2, c), line(self.normal, 1)], district="Sylhet"))
        self.assertEqual(order.shipping_total, 220)                    # 100 campaign + 120 normal "all"
        self.assertEqual(order.total_cost, d(900 * 2 + 500) + 220)
        bd = order.delivery_breakdown
        self.assertEqual((bd["district"], bd["total"]), ("Sylhet", 220))
        self.assertEqual([(g["label"], g["amount"]) for g in bd["groups"]], [(c.title, 100), ("Regular items", 120)])
        self.assertEqual(bd["groups"][0]["rule"]["config"], {"Dhaka": 60, "all": 100})

    def test_summary_and_order_agree(self):
        c = self.camp(delivery_basis="PER_PRODUCT", mixed_cart_delivery="SEPARATE")
        items = [line(self.p1, 1, c), line(self.p2, 1, c), line(self.normal, 1)]
        summary_total = d(self.summary(items, district="Dhaka").json()["data"]["delivery_charge"])
        order = self.order_of(self.place(items, district="Dhaka"))
        self.assertEqual(order.shipping_total, summary_total)

    # ---- no campaign = exactly the old behaviour ----
    def test_a_cart_without_a_custom_campaign_keeps_the_existing_delivery(self):
        total, bd, data = self.delivery([line(self.p1, 1), line(self.p2, 1)], "Dhaka")
        self.assertEqual(total, 120)
        self.assertEqual([i["delivery_charge"] for i in data["items"]], [60.0, 60.0])     # per-item numbers still there
        self.assertEqual(bd["groups"][0]["label"], "Regular items")
        order = self.order_of(self.place([line(self.p1, 1), line(self.p2, 1)], district="Dhaka"))
        self.assertEqual(order.shipping_total, 120)
        # Task 5: every order now stores the counting rule used (no campaign data in it)
        self.assertEqual(order.delivery_breakdown["groups"][0]["count_mode"], "PRODUCT_WISE")
        self.assertEqual([g["type"] for g in order.delivery_breakdown["groups"]], ["normal"])

    def test_without_a_district_a_normal_cart_still_uses_the_existing_range_logic(self):
        data = self.summary([line(self.p1, 1)]).json()["data"]
        self.assertEqual(d(data["delivery_charge"]), 60)
        self.assertEqual(data["delivery_info"]["max"], 120.0)


# ==========================================================================
# GIFTS (SPEC 12)
# ==========================================================================
SWITCH_TABLE = [
    (False, SW.INHERIT, False), (True, SW.INHERIT, True),
    (False, SW.INCLUDE, True), (True, SW.INCLUDE, True),
    (False, SW.EXCLUDE, False), (True, SW.EXCLUDE, False),
]


class CampaignGiftTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.p = shop_product(price=1000)
        self.gift = make_gift_for(self.p)
        self.gift.inventory_quantity = 50
        self.gift.save()

    def gift_rows(self, items):
        return [i for i in items if i.get("is_gift")]

    def test_gifts_off_by_default_no_gift_line_in_summary_or_order(self):
        c = make_campaign()
        add(c, self.p, DT.PERCENT, 20)
        items = self.summary([line(self.p, 2, c)]).json()["data"]["items"]
        self.assertEqual(self.gift_rows(items), [])
        order = self.order_of(self.place([line(self.p, 2, c)]))
        self.assertEqual(order.order_items.count(), 1)
        self.gift.refresh_from_db()
        self.assertEqual(self.gift.inventory_quantity, 50)                # the gift stock was not touched

    def test_every_inherit_include_exclude_combination_in_summary_and_order(self):
        for camp_on, mode, expected in SWITCH_TABLE:
            with self.subTest(campaign_switch=camp_on, mode=mode):
                Campaign.objects.all().delete()
                Order.objects.all().delete()
                c = make_campaign(include_product_gifts=camp_on)
                add(c, self.p, DT.PERCENT, 20, gift_mode=mode)
                gifts = self.gift_rows(self.summary([line(self.p, 2, c)]).json()["data"]["items"])
                self.assertEqual(len(gifts), 1 if expected else 0)
                order = self.order_of(self.place([line(self.p, 2, c)]))
                self.assertEqual(order.order_items.filter(snapshot__is_gift=True).count(), 1 if expected else 0)
                self.assertEqual(self.campaign_item(order).snapshot["campaign_gifts_included"], expected)

    def test_gifts_on_the_gift_line_appears_exactly_as_today(self):
        c = make_campaign(include_product_gifts=True)
        add(c, self.p, DT.PERCENT, 20)
        gift = self.gift_rows(self.summary([line(self.p, 3, c)]).json()["data"]["items"])[0]
        self.assertEqual((gift["quantity"], gift["price"], gift["gift_type"], gift["reference_product_id"]),
                         (3, 0, "FREE", self.p.id))
        order = self.order_of(self.place([line(self.p, 3, c)]))
        gift_item = order.order_items.get(snapshot__is_gift=True)
        self.assertEqual((gift_item.quantity, gift_item.discount_price, gift_item.product_id), (3, Decimal("0"), self.gift.id))
        self.gift.refresh_from_db()
        self.assertEqual(self.gift.inventory_quantity, 47)

    def test_gift_lines_never_get_campaign_fields(self):
        c = make_campaign(include_product_gifts=True)
        add(c, self.p, DT.PERCENT, 20)
        order = self.order_of(self.place([line(self.p, 1, c)]))
        gift_item = order.order_items.get(snapshot__is_gift=True)
        self.assertIsNone(gift_item.campaign)
        self.assertIsNone(gift_item.campaign_name)
        self.assertIsNone(gift_item.regular_price)
        self.assertNotIn("campaign", gift_item.snapshot)
        self.assertNotIn("campaign_pricing", gift_item.snapshot)

    def test_normal_line_of_the_same_product_still_gets_its_gift(self):
        c = make_campaign(include_product_gifts=False)
        add(c, self.p, DT.PERCENT, 20)
        items = self.summary([line(self.p, 2, c), line(self.p, 3)]).json()["data"]["items"]
        gifts = self.gift_rows(items)
        self.assertEqual([g["quantity"] for g in gifts], [3])             # only the normal line's quantity
        order = self.order_of(self.place([line(self.p, 2, c), line(self.p, 3)]))
        self.assertEqual([i.quantity for i in order.order_items.filter(snapshot__is_gift=True)], [3])

    def test_normal_cart_gifts_are_unchanged(self):
        items = self.summary([line(self.p, 2)]).json()["data"]["items"]
        self.assertEqual(len(self.gift_rows(items)), 1)

    def campaign_item(self, order):
        return order.order_items.get(campaign__isnull=False)


# ==========================================================================
# OFFERS (SPEC 12)
# ==========================================================================
class CampaignOfferTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.p = shop_product(price=1000)
        self.free = shop_product(price=100, name="Free Pencil")
        self.offer = Offer.objects.create(name="Buy 2 get 1", apply_to_all=True, gift_mode=OFFER_GIFT_MODE.AUTO)
        self.tier = OfferTier.objects.create(offer=self.offer, buy_qty=2, free_qty=1)
        OfferGift.objects.create(offer=self.offer, product=self.free, quantity=1)

    def offer_gifts(self, items):
        return [i for i in items if i.get("is_gift") and i.get("offer_id")]

    def offer_entry(self, data):
        return next((o for o in data["offers"] if o["id"] == self.offer.id), None)

    def test_offers_off_by_default_the_campaign_quantity_earns_nothing(self):
        c = make_campaign()
        add(c, self.p, DT.PERCENT, 20)
        data = self.summary([line(self.p, 2, c)]).json()["data"]
        self.assertEqual(self.offer_gifts(data["items"]), [])
        self.assertIsNone(self.offer_entry(data))                          # no card, no nudge mentions the line
        order = self.order_of(self.place([line(self.p, 2, c)]))
        self.assertEqual(order.order_items.filter(snapshot__source="offer").count(), 0)

    def test_every_inherit_include_exclude_combination(self):
        for camp_on, mode, expected in SWITCH_TABLE:
            with self.subTest(campaign_switch=camp_on, mode=mode):
                Campaign.objects.all().delete()
                Order.objects.all().delete()
                c = make_campaign(include_offers=camp_on)
                add(c, self.p, DT.PERCENT, 20, offer_mode=mode)
                data = self.summary([line(self.p, 2, c)]).json()["data"]
                self.assertEqual(len(self.offer_gifts(data["items"])), 1 if expected else 0)
                order = self.order_of(self.place([line(self.p, 2, c)]))
                self.assertEqual(order.order_items.filter(snapshot__source="offer").count(), 1 if expected else 0)
                item = order.order_items.get(campaign__isnull=False)
                self.assertEqual(item.snapshot["campaign_offers_included"], expected)

    def test_offers_on_behaves_exactly_like_a_normal_line(self):
        c = make_campaign(include_offers=True)
        add(c, self.p, DT.PERCENT, 20)
        normal = self.offer_gifts(self.summary([line(self.p, 2)]).json()["data"]["items"])
        campaign = self.offer_gifts(self.summary([line(self.p, 2, c)]).json()["data"]["items"])
        self.assertEqual([(g["product_id"], g["quantity"]) for g in normal], [(g["product_id"], g["quantity"]) for g in campaign])

    def test_normal_line_of_the_same_product_still_earns_the_offer(self):
        c = make_campaign(include_offers=False)
        add(c, self.p, DT.PERCENT, 20)
        self.assertEqual(len(self.offer_gifts(self.summary([line(self.p, 2)]).json()["data"]["items"])), 1)

    def test_excluded_campaign_line_does_not_count_toward_a_tier_together_with_a_normal_line(self):
        # 2 campaign (excluded) + 1 normal = 3, but only the normal 1 counts: no tier reached
        c = make_campaign(include_offers=False)
        add(c, self.p, DT.PERCENT, 20)
        data = self.summary([line(self.p, 2, c), line(self.p, 1)]).json()["data"]
        self.assertEqual(self.offer_gifts(data["items"]), [])
        entry = self.offer_entry(data)
        self.assertEqual(entry["qualifying_qty"], 1)
        self.assertEqual(entry["next_tier"]["need_more"], 1)               # the nudge ignores the campaign line
        order = self.order_of(self.place([line(self.p, 2, c), line(self.p, 1)]))
        self.assertEqual(order.order_items.filter(snapshot__source="offer").count(), 0)

    def test_only_the_normal_quantity_counts_when_it_is_enough(self):
        c = make_campaign(include_offers=False)
        add(c, self.p, DT.PERCENT, 20)
        data = self.summary([line(self.p, 1, c), line(self.p, 2)]).json()["data"]
        self.assertEqual(len(self.offer_gifts(data["items"])), 1)
        self.assertEqual(self.offer_entry(data)["qualifying_qty"], 2)

    def test_included_campaign_line_counts_together_with_a_normal_line(self):
        c = make_campaign(include_offers=True)
        add(c, self.p, DT.PERCENT, 20)
        data = self.summary([line(self.p, 1, c), line(self.p, 1)]).json()["data"]
        self.assertEqual(len(self.offer_gifts(data["items"])), 1)

    def test_offer_picks_for_an_offer_that_no_longer_earns_are_handled_like_a_reduced_quantity(self):
        choose = Offer.objects.create(name="Pick one", apply_to_all=True, gift_mode=OFFER_GIFT_MODE.CHOOSE)
        tier = OfferTier.objects.create(offer=choose, buy_qty=2, free_qty=1)
        OfferGift.objects.create(offer=choose, product=self.free, tier=tier, quantity=1)
        self.offer.is_active = False
        self.offer.save()
        picks = {str(choose.id): [{"product_id": self.free.id, "quantity": 1}]}
        c = make_campaign(include_offers=False)
        add(c, self.p, DT.PERCENT, 20)
        # excluded: nothing earned, the pick is ignored exactly as for a reduced quantity (no error, no free item)
        order = self.order_of(self.place([line(self.p, 2, c)], offer_picks=picks))
        self.assertEqual(order.order_items.filter(snapshot__source="offer").count(), 0)
        # included: the same pick is accepted
        Campaign.objects.filter(pk=c.pk).update(include_offers=True)
        order = self.order_of(self.place([line(self.p, 2, c)], offer_picks=picks))
        self.assertEqual(order.order_items.filter(snapshot__source="offer").count(), 1)

    def test_offer_free_items_never_get_campaign_fields_and_are_not_counted(self):
        c = make_campaign(include_offers=True)
        add(c, self.p, DT.PERCENT, 20, stock_limit=10)
        order = self.order_of(self.place([line(self.p, 2, c)]))
        free = order.order_items.get(snapshot__source="offer")
        self.assertIsNone(free.campaign)
        self.assertIsNone(free.campaign_name)
        self.assertNotIn("campaign", free.snapshot)
        stats = get_campaign_sales_stats([c.id])[c.id]
        self.assertEqual((stats["orders"], stats["units"], stats["revenue"]), (1, 2, Decimal("1600")))
        cp = CampaignProduct.objects.get(campaign=c)
        from .pricing import get_sold_units
        self.assertEqual(get_sold_units(cp), 2)

    def test_the_summary_and_place_order_use_one_helper(self):
        # both call sites go through campaigns.checkout.offer_engine_lines
        import inspect
        from order import api_views
        source = inspect.getsource(api_views)
        self.assertEqual(source.count("campaign_checkout.offer_engine_lines("), 2)
        from .checkout import offer_engine_lines
        rows = [{"product_id": 1, "variant_id": None, "quantity": 2, "offers_included": False},
                {"product_id": 2, "variant_id": None, "quantity": 1, "offers_included": True},
                {"product_id": 3, "variant_id": None, "quantity": 4}]
        self.assertEqual([r["product_id"] for r in offer_engine_lines(rows)], [2, 3])


# ==========================================================================
# STATS (SPEC 9 COUNTS)
# ==========================================================================
class CampaignStatsTests(CheckoutBase):
    def test_orders_units_and_revenue_exclude_cancelled_orders(self):
        p = shop_product(price=1000)
        c = make_campaign()
        add(c, p, DT.PERCENT, 20)
        o1 = self.order_of(self.place([line(p, 2, c)]))
        self.order_of(self.place([line(p, 1, c), line(p, 5)]))          # a normal line in the same order
        stats = get_campaign_sales_stats([c.id])[c.id]
        self.assertEqual((stats["orders"], stats["units"], stats["revenue"]), (2, 3, Decimal("2400")))
        from pencilwoodbd.choices import STATUS
        Order.objects.filter(pk=o1.pk).update(status=STATUS.CANCELLED)
        stats = get_campaign_sales_stats([c.id])[c.id]
        self.assertEqual((stats["orders"], stats["units"], stats["revenue"]), (1, 1, Decimal("800")))

    def test_campaign_with_no_orders_has_no_entry(self):
        c = make_campaign()
        self.assertEqual(get_campaign_sales_stats([c.id]), {})
