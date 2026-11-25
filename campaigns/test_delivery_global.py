"""
Task 5 tests: global delivery counting rule (per product / per order). Run: python manage.py test campaigns
"""
from decimal import Decimal

from django.test import Client

from authentication.models import Customer, CustomUser
from pencilwoodbd.choices import CAMPAIGN_DISCOUNT_TYPE as DT, USER_TYPE
from product.models import ProductDeliveryCharge
from site_app.api_views import LandingPageOrderAPI
from site_app.delivery_charge import DeliveryChargeResolver, compute_regular_charge
from site_app.models import SiteDeliveryChargeConfig

from .order_display import delivery_rule_view
from .test_checkout import PHONE, CheckoutBase, line, shop_product
from .tests import add, make_campaign, make_gift_for, make_variant


def d(value):
    return Decimal(str(value))


def set_rule(mode="PRODUCT_WISE", source="GLOBAL", area=None):
    SiteDeliveryChargeConfig.objects.update_or_create(pk=1, defaults={
        "count_mode": mode, "order_wise_amount_source": source,
        "area_and_charge": {"all": 80} if area is None else area})


class Base(CheckoutBase):
    def setUp(self):
        super().setUp()
        set_rule()
        self.cradle = shop_product(price=1000, name="Cradle")
        self.v1 = make_variant(self.cradle, price=1000, default=True)
        self.v2 = make_variant(self.cradle, price=1100)
        self.masala = shop_product(price=500, name="Masala")
        ProductDeliveryCharge.objects.create(product=self.cradle, area_and_charge={"all": 100})
        ProductDeliveryCharge.objects.create(product=self.masala, area_and_charge={"all": 60})

    def cart(self):
        return [line(self.cradle, 1, variant=self.v1), line(self.cradle, 2, variant=self.v2), line(self.masala, 1)]

    def data(self, items=None, district="Dhaka"):
        res = self.summary(items or self.cart(), district=district)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["data"]

    def charge(self, items=None, district="Dhaka"):
        return d(self.data(items, district)["delivery_charge"])


class CountingRuleTests(Base):
    def test_same_product_with_two_variants_counts_once(self):
        items = [line(self.cradle, 1, variant=self.v1), line(self.cradle, 3, variant=self.v2)]
        data = self.data(items)
        self.assertEqual(d(data["delivery_charge"]), 100)
        self.assertEqual([r["delivery_charge"] for r in data["items"]], [100, 0])      # charge on the first row only

    def test_product_wise_sums_distinct_products(self):
        data = self.data()
        self.assertEqual(d(data["delivery_charge"]), 160)
        self.assertEqual([r["delivery_charge"] for r in data["items"]], [100, 0, 60])
        self.assertEqual(data["delivery_info"]["count_mode"], "PRODUCT_WISE")

    def test_order_wise_global_lowest_highest(self):
        for source, expected in (("GLOBAL", 80), ("LOWEST", 60), ("HIGHEST", 100)):
            set_rule("ORDER_WISE", source)
            data = self.data()
            self.assertEqual(d(data["delivery_charge"]), expected, source)
            self.assertEqual(d(data["grand_total"]), d(data["subtotal"]) + expected)
            self.assertTrue(all(r["delivery_charge"] == 0 for r in data["items"]))
            self.assertEqual(data["delivery_info"]["count_mode"], "ORDER_WISE")
            self.assertEqual(data["delivery_info"]["order_wise_amount_source"], source)
            group = data["delivery_breakdown"]["groups"][0]
            self.assertEqual((group["label"], group["amount"], len(group["lines"])), ("Regular items", expected, 1))
            self.assertEqual(group["lines"][0]["amount"], expected)

    def test_zero_charge_product_counts_as_zero(self):
        ProductDeliveryCharge.objects.filter(product=self.masala).update(area_and_charge={"all": 0})
        self.assertEqual(self.charge(), 100)                       # product wise: 100 + 0
        set_rule("ORDER_WISE", "LOWEST")
        self.assertEqual(self.charge(), 0)                         # the order becomes free
        set_rule("ORDER_WISE", "HIGHEST")
        self.assertEqual(self.charge(), 100)

    def test_free_gift_lines_are_never_counted(self):
        gift = make_gift_for(self.masala)
        ProductDeliveryCharge.objects.create(product=gift, area_and_charge={"all": 500})
        items = [line(self.masala, 1)]
        for mode, source, expected in (("PRODUCT_WISE", "GLOBAL", 60), ("ORDER_WISE", "HIGHEST", 60),
                                       ("ORDER_WISE", "LOWEST", 60)):
            set_rule(mode, source)
            data = self.data(items)
            self.assertTrue(any(r.get("is_gift") for r in data["items"]))
            self.assertEqual(d(data["delivery_charge"]), expected)

    def test_district_specific_amounts_use_the_existing_resolver(self):
        ProductDeliveryCharge.objects.filter(product=self.cradle).update(area_and_charge={"Dhaka": 40, "all": 100})
        set_rule("ORDER_WISE", "LOWEST", {"Dhaka": 70, "all": 90})
        self.assertEqual(self.charge(district="Dhaka"), 40)
        self.assertEqual(self.charge(district="Sylhet"), 60)
        set_rule("ORDER_WISE", "GLOBAL", {"Dhaka": 70, "all": 90})
        self.assertEqual(self.charge(district="Dhaka"), 70)
        self.assertEqual(self.charge(district="Sylhet"), 90)


class SameNumberEverywhereTests(Base):
    def test_guest_summary_equals_cart_summary_equals_place_order(self):
        user = CustomUser.objects.create(email="b@example.com", phone=PHONE, username="b")
        Customer.objects.create(user=user, name="B", phone=PHONE)
        for mode, source, expected in (("PRODUCT_WISE", "GLOBAL", 160), ("ORDER_WISE", "GLOBAL", 80),
                                       ("ORDER_WISE", "LOWEST", 60), ("ORDER_WISE", "HIGHEST", 100)):
            set_rule(mode, source)
            guest = self.charge()
            # logged-in cart
            self.client.force_authenticate(user)
            ids = []
            for it in self.cart():
                body = {"product_id": it["product_id"], "quantity": it["quantity"]}
                if it["variant_id"]:
                    body["variant_id"] = it["variant_id"]
                self.assertEqual(self.client.post("/cart/add/", body, format="json").status_code, 200)
            from product.models import AddToCart
            ids = list(AddToCart.objects.filter(customer__user=user).values_list("id", flat=True))
            res = self.client.get("/api/checkout/summary/", {"cart_ids": ids, "district": "Dhaka"})
            cart = d(res.json()["data"]["delivery_charge"])
            AddToCart.objects.all().delete()
            self.client.force_authenticate(None)
            order = self.order_of(self.place(self.cart(), "Dhaka"))
            self.assertEqual((guest, cart, order.shipping_total), (expected, expected, expected), (mode, source))
            self.assertEqual(order.total_cost, order.shipping_total + sum(
                i.discount_price * i.quantity for i in order.order_items.all()))
            rule = order.delivery_breakdown["groups"][0]
            self.assertEqual(rule["count_mode"], mode)
            self.assertTrue(rule["explanation"])

    def test_place_order_stores_the_rule_for_the_dashboard(self):
        set_rule("ORDER_WISE", "LOWEST")
        order = self.order_of(self.place(self.cart(), "Dhaka"))
        view = delivery_rule_view(order)
        self.assertEqual(view["regular_amount"], 60)
        self.assertIn("lowest", view["source_text"])
        self.assertIn("Cradle", view["explanation"])
        self.assertEqual(delivery_rule_view(type("O", (), {"delivery_breakdown": {}})()), None)


class EstimateTests(Base):
    def setUp(self):
        super().setUp()
        ProductDeliveryCharge.objects.filter(product=self.cradle).update(area_and_charge={"Dhaka": 40, "all": 100})
        ProductDeliveryCharge.objects.filter(product=self.masala).update(area_and_charge={"Dhaka": 20, "all": 60})
        SiteDeliveryChargeConfig.objects.filter(pk=1).update(area_and_charge={"Dhaka": 30, "all": 90})

    def test_product_wise_estimate_is_the_cheapest_district_sum(self):
        data = self.data(district=None)
        self.assertEqual(d(data["delivery_charge"]), 60)
        self.assertEqual((data["delivery_info"]["min"], data["delivery_info"]["max"]), (60, 160))
        self.assertEqual([r["delivery_charge"] for r in data["items"]], [40, 0, 20])

    def test_order_wise_estimate_range(self):
        for source, lo, hi in (("GLOBAL", 30, 90), ("LOWEST", 20, 60), ("HIGHEST", 40, 100)):
            SiteDeliveryChargeConfig.objects.filter(pk=1).update(count_mode="ORDER_WISE", order_wise_amount_source=source)
            data = self.data(district=None)
            self.assertEqual((d(data["delivery_charge"]), data["delivery_info"]["min"], data["delivery_info"]["max"]), (lo, lo, hi), source)
            self.assertTrue(all(r["delivery_charge"] == 0 for r in data["items"]))
            from product.models import Product
            fresh = list(Product.objects.select_related("delivery_charge").filter(pk__in=[self.cradle.pk, self.masala.pk]))
            rng = DeliveryChargeResolver.cart_range(fresh)
            self.assertEqual((rng["min"], rng["max"]), (lo, hi))


class MixedCartTests(Base):
    def camp(self, **kw):
        defaults = dict(delivery_mode="CUSTOM", delivery_amount_source="SAME_FOR_ALL", delivery_config={"all": 70},
                        delivery_basis="PER_ORDER", mixed_cart_delivery="COMBINED")
        defaults.update(kw)
        c = make_campaign(**defaults)
        self.special = shop_product(price=2000, name="Special")
        add(c, self.special, DT.PERCENT, 10)
        return c

    def test_default_rule_keeps_combined_and_separate(self):
        c = self.camp()
        items = [line(self.special, 1, c), line(self.cradle, 1, variant=self.v1), line(self.masala, 1)]
        data = self.data(items)
        self.assertEqual(d(data["delivery_charge"]), 70)                 # COMBINED: regular items add nothing
        self.assertTrue(data["delivery_breakdown"]["groups"][1]["waived"])
        self.assertTrue(all(r["delivery_charge"] == 0 for r in data["items"]))
        from campaigns.models import Campaign
        Campaign.objects.filter(pk=c.pk).update(mixed_cart_delivery="SEPARATE")
        data = self.data(items)
        self.assertEqual(d(data["delivery_charge"]), 70 + 160)           # campaign 70 + regular 100 + 60

    def test_order_wise_only_changes_the_regular_group(self):
        c = self.camp(mixed_cart_delivery="SEPARATE")
        items = [line(self.special, 1, c), line(self.cradle, 1, variant=self.v1), line(self.masala, 1)]
        for source, regular in (("GLOBAL", 80), ("LOWEST", 60), ("HIGHEST", 100)):
            set_rule("ORDER_WISE", source)
            data = self.data(items)
            self.assertEqual(d(data["delivery_charge"]), 70 + regular, source)      # campaign group still 70
            groups = data["delivery_breakdown"]["groups"]
            self.assertEqual([g["amount"] for g in groups], [70, regular])
            order = self.order_of(self.place(items, "Dhaka"))
            self.assertEqual(order.shipping_total, 70 + regular)

    def test_campaign_with_normal_delivery_is_part_of_the_regular_group(self):
        c = self.camp(delivery_mode="NORMAL", delivery_config={})
        items = [line(self.special, 1, c), line(self.masala, 1)]
        set_rule("ORDER_WISE", "HIGHEST")
        ProductDeliveryCharge.objects.create(product=self.special, area_and_charge={"all": 150})
        self.assertEqual(self.charge(items), 150)
        set_rule("PRODUCT_WISE")
        self.assertEqual(self.charge(items), 210)


class DefaultConfigSnapshotTests(Base):
    """With the default settings the totals are exactly what the old code produced (each distinct product once)."""

    def old_total(self, products, district):
        total = Decimal("0")
        for p in products:
            total += DeliveryChargeResolver.get_charge(p, district)
        return total

    def test_defaults_match_the_old_algorithm(self):
        cfg = SiteDeliveryChargeConfig.get_solo()
        self.assertEqual((cfg.count_mode, cfg.order_wise_amount_source), ("PRODUCT_WISE", "GLOBAL"))
        plain = shop_product(price=300, name="Plain")                    # no product charge: global applies
        SiteDeliveryChargeConfig.objects.filter(pk=1).update(area_and_charge={"Dhaka": 60, "all": 120})
        carts = [[self.cradle], [self.masala], [self.cradle, self.masala], [plain], [self.cradle, plain, self.masala]]
        for district in ("Dhaka", "Sylhet", "dhaka"):
            for products in carts:
                items = []
                for p in products:
                    items.append(line(p, 2, variant=self.v1) if p == self.cradle else line(p, 2))
                if self.cradle in products:
                    items.append(line(self.cradle, 1, variant=self.v2))      # extra variant line of the same product
                self.assertEqual(self.charge(items, district), self.old_total(products, district), (district, products))
                self.assertEqual(compute_regular_charge(products, district)["amount"], self.old_total(products, district))
        # hard-coded snapshot
        self.assertEqual(self.charge([line(self.cradle, 1, variant=self.v1), line(self.masala, 1), line(plain, 1)], "Dhaka"), 220)
        self.assertEqual(self.charge([line(plain, 1)], "Sylhet"), 120)


class LandingPathsTests(Base):
    def test_landing_order_paths_are_not_affected_by_the_setting(self):
        """The landing pages keep their own fixed charges (60 / 120 / 150) whatever the global rule says."""
        for mode, source in (("PRODUCT_WISE", "GLOBAL"), ("ORDER_WISE", "LOWEST")):
            set_rule(mode, source)
            data = {"unit_price": 500, "subtotal": 500, "district": "Dhaka", "delivery": 60, "total": 560, "quantity": 1}
            total, qty, sub, delivery = LandingPageOrderAPI().check_order_amount(None, self.masala, data)
            self.assertEqual((total, qty, sub, delivery), (560, 1, 500, 60.0))
            data.update(delivery=100, total=600)
            with self.assertRaises(ValueError):
                LandingPageOrderAPI().check_order_amount(None, self.masala, data)


class ProductPageTests(Base):
    def info(self, district=None):
        q = {"district": district} if district else {}
        res = self.client.get(f"/api/ecom/products/{self.cradle.slug}/", q)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["data"]["delivery_info"]

    def test_product_page_shows_the_charge_of_an_order_with_only_this_product(self):
        self.assertEqual(self.info()["charge"], None)
        for mode, source, expected in (("PRODUCT_WISE", "GLOBAL", 100), ("ORDER_WISE", "GLOBAL", 80),
                                       ("ORDER_WISE", "LOWEST", 100), ("ORDER_WISE", "HIGHEST", 100)):
            set_rule(mode, source)
            info = self.info("Dhaka")
            self.assertEqual((info["charge"], info["count_mode"]), (expected, mode))


class DashboardSettingTests(Base):
    URL = "/dashboard/settings/delivery-charge/"

    def staff(self, kind=USER_TYPE.ADMIN):
        n = CustomUser.objects.count() + 1
        user = CustomUser.objects.create(email=f"s{n}@example.com", username=f"s{n}", user_type=kind)
        client = Client()
        client.force_login(user)
        return client

    def url(self):
        from django.urls import reverse
        return reverse("delivery_charge_settings")

    def test_saving_and_reading_the_rule(self):
        client = self.staff()
        res = client.post(self.url(), {"count_mode": "ORDER_WISE", "order_wise_amount_source": "HIGHEST",
                                       "delivery_charge_json": '{"mode":"all","all":"90"}'})
        self.assertEqual(res.status_code, 302)
        cfg = SiteDeliveryChargeConfig.get_solo()
        self.assertEqual((cfg.count_mode, cfg.order_wise_amount_source, cfg.area_and_charge), ("ORDER_WISE", "HIGHEST", {"all": "90"}))
        page = client.get(self.url())
        self.assertEqual(page.context["delivery_count_mode"], "ORDER_WISE")
        self.assertEqual(page.context["delivery_order_wise_source"], "HIGHEST")
        html = page.content.decode()
        self.assertIn("How should delivery charge be counted?", html)
        self.assertIn("Which charge should the order use?", html)
        self.assertIn('value="HIGHEST" selected', html)

    def test_bad_value_saves_nothing_and_missing_fields_keep_the_old_rule(self):
        client = self.staff()
        client.post(self.url(), {"count_mode": "ORDER_WISE", "order_wise_amount_source": "LOWEST"})
        client.post(self.url(), {"count_mode": "NONSENSE"})
        self.assertEqual(SiteDeliveryChargeConfig.get_solo().count_mode, "ORDER_WISE")
        client.post(self.url(), {"delivery_charge_json": '{"mode":"none"}'})       # an old form that sends no rule
        cfg = SiteDeliveryChargeConfig.get_solo()
        self.assertEqual((cfg.count_mode, cfg.order_wise_amount_source), ("ORDER_WISE", "LOWEST"))

    def test_staff_cannot_change_the_rule(self):
        client = self.staff(USER_TYPE.STAFF)
        client.post(self.url(), {"count_mode": "ORDER_WISE"})
        self.assertEqual(SiteDeliveryChargeConfig.get_solo().count_mode, "PRODUCT_WISE")
