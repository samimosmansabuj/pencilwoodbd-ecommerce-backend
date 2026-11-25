"""
Task 3 tests (part 1): the Campaigns dashboard - permissions, list, form pages, validation, overlap, gift/offer
fields, images, pause/resume, duplicate, delete, product picker.
Part 2: test_dashboard_orders.py (order screens) and test_popup.py (popups).   Run: python manage.py test campaigns
"""
import itertools
import json
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from authentication.models import CustomUser
from campaigns import dashboard as logic
from campaigns.models import Campaign, CampaignProduct, CampaignProductVariant
from offers.models import Offer, OfferTier
from pencilwoodbd.choices import USER_TYPE
from product.models import Category

from .tests import add, make_campaign, make_gift_for, make_product, make_variant

_n = itertools.count(1)


def local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def make_user(user_type=USER_TYPE.STAFF):
    n = next(_n)
    return CustomUser.objects.create(email=f"user{n}@example.com", username=f"user{n}", user_type=user_type)


def login(user_type=USER_TYPE.STAFF):
    client = Client()
    user = make_user(user_type)
    client.force_login(user)
    client.user = user
    return client


def png(name="banner.png", size=(120, 60), color="red"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def row(product, **kw):
    data = {"product_id": product.id, "discount_type": "PERCENT", "discount_value": "20", "variant_mode": "ALL_SAME",
            "stock_limit": "", "gift_mode": "INHERIT", "offer_mode": "INHERIT", "delivery_config": None, "variants": []}
    data.update(kw)
    return data


def payload(products=None, **over):
    now = timezone.now()
    data = {
        "title": f"Sale {next(_n)}", "slug": "", "short_description": "", "hero_title": "", "hero_subtitle": "",
        "hero_button_text": "", "sort_order": "0", "show_on_home": "0",
        "start_at": local(now + timedelta(hours=1)), "end_at": local(now + timedelta(days=3)),
        "discount_base": "CURRENT", "strike_price_display": "CURRENT", "badge_mode": "DISCOUNT_ONLY", "badge_label": "",
        "allow_coupon": "0", "include_product_gifts": "0", "include_offers": "0", "allow_overlap": "0",
        "delivery_mode": "NORMAL", "delivery_amount_source": "SAME_FOR_ALL", "delivery_basis": "PER_ORDER",
        "mixed_cart_delivery": "COMBINED", "delivery_config": "{}",
        "products": json.dumps(products if products is not None else []), "publish": "0",
    }
    for k, v in over.items():
        data[k] = json.dumps(v) if k in ("delivery_config",) and not isinstance(v, str) else v
    return data


def sellable(price=1000, discount=0, **kw):
    return make_product(price=price, discount=discount, inventory_quantity=50, **kw)


class DashboardBase(TestCase):
    def setUp(self):
        self.staff = login()

    def save(self, data, client=None, **files):
        return (client or self.staff).post(reverse("campaign_save"), {**data, **files})

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def fail(self, response):
        self.assertEqual(response.status_code, 400, response.content)
        return response.json()

    def errors_text(self, response):
        body = self.fail(response)
        return " | ".join(m for msgs in body["errors"].values() for m in msgs)


# ==========================================================================
# PERMISSIONS
# ==========================================================================
class PermissionTests(DashboardBase):
    URLS_GET = ["campaign_list", "campaign_add", "campaign_product_search", "popup_list"]

    def test_anonymous_is_sent_to_the_login_page(self):
        anon = Client()
        for name in self.URLS_GET:
            res = anon.get(reverse(name))
            self.assertEqual(res.status_code, 302, name)
            self.assertIn("login", res["Location"].lower(), name)
        self.assertEqual(anon.post(reverse("campaign_save"), payload()).status_code, 302)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_a_customer_account_is_forbidden_everywhere(self):
        customer = login(USER_TYPE.CUSTOMER)
        c = make_campaign()
        for name in self.URLS_GET:
            self.assertEqual(customer.get(reverse(name)).status_code, 403, name)
        for url in (reverse("campaign_save"), reverse("campaign_toggle", args=[c.id]),
                    reverse("campaign_duplicate", args=[c.id]), reverse("campaign_delete", args=[c.id]),
                    reverse("popup_save")):
            self.assertEqual(customer.post(url, {}).status_code, 403, url)
        self.assertEqual(Campaign.objects.count(), 1)

    def test_staff_admin_and_super_admin_can_open_the_pages(self):
        for role in (USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN):
            client = login(role)
            for name in self.URLS_GET:
                self.assertEqual(client.get(reverse(name)).status_code, 200, (role, name))

    def test_sidebar_has_the_campaigns_and_popups_entries(self):
        html = self.staff.get(reverse("campaign_list")).content.decode()
        self.assertIn(reverse("campaign_list"), html)
        self.assertIn(reverse("popup_list"), html)
        self.assertIn(">Popups<", html.replace("\n", "").replace("  ", "").replace("<i class=\"material-icons-outlined\">arrow_right</i>", ""))


# ==========================================================================
# LIST PAGE
# ==========================================================================
class ListTests(DashboardBase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.live = make_campaign(title="Alpha Live")
        self.upcoming = make_campaign(title="Beta Upcoming", start=now + timedelta(days=1), end=now + timedelta(days=2))
        self.ended = make_campaign(title="Gamma Ended", start=now - timedelta(days=3), end=now - timedelta(days=1))
        self.draft = make_campaign(title="Delta Draft", is_active=False)

    def titles(self, response):
        return [r["c"].title for r in response.context["rows"]]

    def test_lists_everything_with_status_chips_and_counts(self):
        res = self.staff.get(reverse("campaign_list"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(sorted(self.titles(res)), ["Alpha Live", "Beta Upcoming", "Delta Draft", "Gamma Ended"])
        statuses = {r["c"].title: r["status"] for r in res.context["rows"]}
        self.assertEqual(statuses, {"Alpha Live": "live", "Beta Upcoming": "upcoming", "Gamma Ended": "ended", "Delta Draft": "draft"})
        self.assertEqual(res.context["counts"], {"all": 4, "live": 1, "upcoming": 1, "ended": 1, "draft": 1})
        html = res.content.decode()
        for word in ("Live", "Upcoming", "Ended", "Draft"):
            self.assertIn(word, html)

    def test_filter_by_each_status(self):
        for status, expected in (("live", ["Alpha Live"]), ("upcoming", ["Beta Upcoming"]),
                                 ("ended", ["Gamma Ended"]), ("draft", ["Delta Draft"])):
            res = self.staff.get(reverse("campaign_list"), {"status": status})
            self.assertEqual(self.titles(res), expected, status)

    def test_search_by_title(self):
        self.assertEqual(self.titles(self.staff.get(reverse("campaign_list"), {"q": "beta"})), ["Beta Upcoming"])
        self.assertEqual(self.titles(self.staff.get(reverse("campaign_list"), {"q": "nothing"})), [])
        self.assertEqual(self.titles(self.staff.get(reverse("campaign_list"), {"q": "Live", "status": "draft"})), [])

    def test_htmx_request_returns_only_the_table_partial(self):
        res = self.staff.get(reverse("campaign_list"), {"status": "live"}, HTTP_HX_REQUEST="true",
                             HTTP_HX_TARGET="campaign-table-wrapper")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("<html", res.content.decode().lower())
        self.assertIn("Alpha Live", res.content.decode())

    def test_products_count_only_counts_active_rows(self):
        add(self.live, sellable())
        add(self.live, sellable())
        add(self.live, sellable(), is_active=False)
        res = self.staff.get(reverse("campaign_list"), {"status": "live"})
        self.assertEqual(res.context["rows"][0]["product_count"], 2)

    def test_pagination(self):
        for i in range(12):
            make_campaign(title=f"Extra {i}")
        res = self.staff.get(reverse("campaign_list"), {"per_page": "5"})
        self.assertEqual(len(res.context["rows"]), 5)
        self.assertEqual(res.context["paginator"].num_pages, 4)


# ==========================================================================
# FORM PAGES
# ==========================================================================
class FormPageTests(DashboardBase):
    def test_new_form_has_the_four_cards_and_every_label(self):
        html = self.staff.get(reverse("campaign_add")).content.decode()
        for text in ("Basic info", "Products &amp; discounts", "Extra settings", "Review &amp; save",
                     "Campaign name", "Starts *", "Ends *", "Big banner", "Show on the home page",
                     "Take the discount from", "Show as struck-through price",
                     "Apply the same discount to all selected products",
                     "Show extra settings", "Allow coupons on campaign items",
                     "Give the product's free gift on campaign items",
                     "get Y free",
                     "Allow these products in another campaign running at the same time",
                     "Same as normal delivery", "Special delivery for this campaign",
                     "Different price for some districts (optional)", "all districts",
                     "Save as draft", "Save &amp; publish"):
            self.assertIn(text, html, text)
        self.assertEqual(html.count('class="num"'), 4)                         # exactly 4 numbered cards
        self.assertIn('class="collapse" id="cpxExtraBody"', html)               # card 3 is collapsed by default

    def test_campaign_list_uses_the_standard_table_markup(self):
        html = self.staff.get(reverse("campaign_list")).content.decode()
        for cls in ("product-table", "table-responsive white-space-nowrap", "table align-middle", "table-light"):
            self.assertIn(cls, html, cls)
        self.assertIn("cpxPauseModal", html)                                    # pausing asks first

    def test_form_and_list_templates_have_no_dimmed_text(self):
        # UI rule C: the dark theme cannot show muted / dimmed text. Guards every campaign, popup and order-block template.
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR) / "dashbaord/templates"
        files = list((base / "db_campaign").rglob("*.html")) + list((base / "db_popup").rglob("*.html")) \
            + [base / "db_order/partial/order_campaign_block.html"]
        banned = ("text-muted", "text-secondary", "text-black-50", "text-body-secondary", "opacity")
        for f in files:
            text = f.read_text(encoding="utf-8")
            for word in banned:
                self.assertNotIn(word, text, f"{word} found in {f.name}")

    def test_new_form_defaults_are_safe(self):
        data = self.staff.get(reverse("campaign_add")).context["form_data"]
        self.assertFalse(data["allow_coupon"])
        self.assertFalse(data["include_product_gifts"])
        self.assertFalse(data["include_offers"])
        self.assertFalse(data["allow_overlap"])
        self.assertFalse(data["is_active"])
        self.assertEqual((data["discount_base"], data["strike_price_display"]), ("CURRENT", "CURRENT"))
        self.assertEqual(data["delivery_mode"], "NORMAL")
        self.assertEqual(data["products"], [])

    def test_edit_form_loads_the_saved_campaign_with_products_and_variants(self):
        c = make_campaign(title="Black Friday", allow_coupon=True, include_product_gifts=True, include_offers=True,
                          delivery_mode="CUSTOM", delivery_config={"Dhaka": 60, "all": 100})
        p = sellable(name="Cradle")
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000)
        cp = add(c, p, "PERCENT", 10, variant_mode="PER_VARIANT", stock_limit=25, gift_mode="INCLUDE", offer_mode="EXCLUDE")
        CampaignProductVariant.objects.create(campaign_product=cp, variant=v1, discount_type="PERCENT", discount_value=15)
        CampaignProductVariant.objects.create(campaign_product=cp, variant=v2, discount_type="FIXED", discount_value=300)

        res = self.staff.get(reverse("campaign_edit", args=[c.id]))
        self.assertEqual(res.status_code, 200)
        data = res.context["form_data"]
        self.assertEqual((data["title"], data["allow_coupon"], data["include_product_gifts"], data["include_offers"]),
                         ("Black Friday", True, True, True))
        self.assertEqual(data["delivery_config"], {"Dhaka": 60, "all": 100})
        prod = data["products"][0]
        self.assertEqual((prod["name"], prod["row"]["variant_mode"], prod["row"]["stock_limit"], prod["row"]["gift_mode"],
                          prod["row"]["offer_mode"]), ("Cradle", "PER_VARIANT", 25, "INCLUDE", "EXCLUDE"))
        self.assertEqual(prod["row"]["variants"][str(v2.id)], {"discount_type": "FIXED", "discount_value": 300})
        self.assertEqual(len(prod["variants"]), 2)

    def test_unknown_campaign_is_404(self):
        self.assertEqual(self.staff.get(reverse("campaign_edit", args=[999])).status_code, 404)

    def test_the_page_script_reads_inputs_through_form_elements(self):
        # form.title would be the tooltip attribute, not the input: a real bug caught while building the form
        html = self.staff.get(reverse("campaign_add")).content.decode()
        self.assertIn("var F = form.elements", html)
        self.assertNotIn("form.title", html)


# ==========================================================================
# SAVE + VALIDATION
# ==========================================================================
class SaveTests(DashboardBase):
    def test_save_as_draft_without_products(self):
        body = self.ok(self.save(payload(title="Draft only")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertFalse(c.is_active)
        self.assertEqual(c.status, "draft")
        self.assertEqual(c.created_by, self.staff.user)
        self.assertEqual(c.slug, "draft-only")
        self.assertEqual(c.badge_label, "Draft only")

    def test_save_and_activate_with_a_product(self):
        p = sellable()
        body = self.ok(self.save(payload([row(p)], publish="1")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertTrue(c.is_active)
        cp = c.campaign_products.get()
        self.assertEqual((cp.product, cp.discount_type, str(cp.discount_value)), (p, "PERCENT", "20.00"))

    def test_schedule_is_saved_in_dhaka_time(self):
        body = self.ok(self.save(payload(start_at="2026-11-27T00:00", end_at="2026-11-30T23:59")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertEqual(timezone.localtime(c.start_at).strftime("%Y-%m-%d %H:%M %Z"), "2026-11-27 00:00 +06")
        self.assertEqual(c.start_at.utcoffset(), timedelta(0))          # stored as UTC (= 18:00 the day before)
        self.assertEqual(c.start_at.hour, 18)

    def test_title_is_required(self):
        self.assertIn("Title is required", self.errors_text(self.save(payload(title="  "))))
        self.assertEqual(Campaign.objects.count(), 0)

    def test_schedule_validation(self):
        now = timezone.now()
        text = self.errors_text(self.save(payload(start_at=local(now + timedelta(days=2)), end_at=local(now + timedelta(days=1)))))
        self.assertIn("End time must be after the start time", text)
        self.assertIn("Start time is required", self.errors_text(self.save(payload(start_at=""))))
        self.assertIn("End time is required", self.errors_text(self.save(payload(end_at=""))))
        self.assertIn("End time must be after", self.errors_text(self.save(payload(start_at="2026-12-01T10:00", end_at="2026-12-01T10:00"))))

    def test_percent_must_be_above_0_and_below_100_and_fixed_above_0(self):
        p = sellable(name="Cradle Chair")
        for kind, value in (("PERCENT", "0"), ("PERCENT", "100"), ("PERCENT", "150"), ("PERCENT", "-5"), ("FIXED", "0"),
                            ("FIXED", "-1"), ("PERCENT", ""), ("PERCENT", "abc")):
            with self.subTest(kind=kind, value=value):
                text = self.errors_text(self.save(payload([row(p, discount_type=kind, discount_value=value)])))
                self.assertIn("Cradle Chair", text)
        self.assertEqual(Campaign.objects.count(), 0)
        self.ok(self.save(payload([row(p, discount_type="PERCENT", discount_value="99.5")])))
        self.ok(self.save(payload([row(p, discount_type="FIXED", discount_value="1")])))

    def test_stock_limit_validation(self):
        p = sellable(name="Limited")
        for bad in ("0", "-3", "abc", "2.5"):
            self.assertIn("stock limit", self.errors_text(self.save(payload([row(p, stock_limit=bad)]))))
        body = self.ok(self.save(payload([row(p, stock_limit="40")])))
        self.assertEqual(CampaignProduct.objects.get(campaign_id=body["id"]).stock_limit, 40)

    def test_product_rows_are_checked(self):
        p = sellable(name="Twice")
        self.assertIn("added twice", self.errors_text(self.save(payload([row(p), row(p)]))))
        draft_product = make_product(name="Not Active", status="Draft")
        self.assertIn("not an active", self.errors_text(self.save(payload([row(draft_product)]))))
        gift = make_product(name="Gift Only", is_gift_only=True)
        self.assertIn("not an active", self.errors_text(self.save(payload([row(gift)]))))
        self.assertIn("no longer exists", self.errors_text(self.save(payload([{**row(p), "product_id": 99999}]))))

    def test_publishing_needs_at_least_one_product_but_a_draft_does_not(self):
        self.assertIn("at least one product", self.errors_text(self.save(payload([], publish="1"))))
        self.ok(self.save(payload([], publish="0")))

    def test_a_draft_with_invalid_discount_is_still_refused(self):
        p = sellable(name="Bad Draft")
        self.fail(self.save(payload([row(p, discount_value="100")], publish="0")))

    def test_slug_is_unique_and_the_error_names_the_other_campaign(self):
        make_campaign(title="Black Friday")
        text = self.errors_text(self.save(payload(slug="black-friday")))
        self.assertIn("Black Friday", text)
        self.assertIn("link name", text.lower())
        body = self.ok(self.save(payload(title="Black Friday", slug="")))          # blank = auto, made unique
        self.assertEqual(Campaign.objects.get(pk=body["id"]).slug, "black-friday-1")

    def test_editing_keeps_the_slug_unless_changed(self):
        body = self.ok(self.save(payload(title="Eid Sale")))
        edit = self.ok(self.save(payload(title="Eid Mega Sale", id=body["id"])))
        self.assertEqual(Campaign.objects.get(pk=edit["id"]).slug, "eid-sale")
        again = self.ok(self.save(payload(title="Eid Mega Sale 2", slug="eid-2026", id=body["id"])))
        self.assertEqual(Campaign.objects.get(pk=again["id"]).slug, "eid-2026")

    def test_editing_updates_in_place_and_removes_dropped_products(self):
        a, b = sellable(name="Keep"), sellable(name="Drop")
        body = self.ok(self.save(payload([row(a), row(b)])))
        self.ok(self.save(payload([row(a, discount_value="35")], title="Renamed", id=body["id"])))
        c = Campaign.objects.get(pk=body["id"])
        self.assertEqual(c.title, "Renamed")
        self.assertEqual([(cp.product.name, str(cp.discount_value)) for cp in c.campaign_products.all()], [("Keep", "35.00")])
        self.assertEqual(Campaign.objects.count(), 1)

    def test_product_order_is_kept(self):
        a, b, c3 = sellable(name="A"), sellable(name="B"), sellable(name="C")
        body = self.ok(self.save(payload([row(c3), row(a), row(b)])))
        names = [cp.product.name for cp in CampaignProduct.objects.filter(campaign_id=body["id"]).order_by("sort_order")]
        self.assertEqual(names, ["C", "A", "B"])

    def test_pricing_and_badge_settings_are_saved(self):
        body = self.ok(self.save(payload(discount_base="REGULAR", strike_price_display="REGULAR",
                                         badge_mode="NAME_AND_DISCOUNT", badge_label="BF")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertEqual((c.discount_base, c.strike_price_display, c.badge_mode, c.badge_label),
                         ("REGULAR", "REGULAR", "NAME_AND_DISCOUNT", "BF"))

    def test_badge_label_is_limited_to_20_characters(self):
        self.assertIn("20 letters", self.errors_text(self.save(payload(badge_label="x" * 21))))

    def test_unknown_choice_values_fall_back_to_safe_defaults(self):
        body = self.ok(self.save(payload(discount_base="HACK", delivery_mode="HACK", badge_mode="HACK")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertEqual((c.discount_base, c.delivery_mode, c.badge_mode), ("CURRENT", "NORMAL", "DISCOUNT_ONLY"))

    def test_the_response_lists_non_blocking_pricing_warnings(self):
        p = sellable(price=1000, discount=800, name="Already Cheap")
        # discount taken from the MAIN price: 10% off 1000 = 900, dearer than today's 800
        body = self.ok(self.save(payload([row(p, discount_value="10")], discount_base="REGULAR", strike_price_display="CURRENT")))
        self.assertEqual(body["warnings"][0]["product"], "Already Cheap")
        self.assertTrue(any("MORE" in w for w in body["warnings"][0]["problems"]))
        clean = self.ok(self.save(payload([row(sellable(name="Fine"))])))
        self.assertEqual(clean["warnings"], [])


# ==========================================================================
# GIFTS & OFFERS FIELDS (SPEC 12)
# ==========================================================================
class GiftOfferFieldTests(DashboardBase):
    def test_campaign_switches_and_product_modes_are_saved_and_reloaded(self):
        p1, p2, p3 = sellable(name="One"), sellable(name="Two"), sellable(name="Three")
        body = self.ok(self.save(payload(
            [row(p1, gift_mode="INCLUDE", offer_mode="EXCLUDE"), row(p2, gift_mode="EXCLUDE", offer_mode="INCLUDE"), row(p3)],
            include_product_gifts="1", include_offers="1")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertTrue(c.include_product_gifts)
        self.assertTrue(c.include_offers)
        modes = {cp.product.name: (cp.gift_mode, cp.offer_mode) for cp in c.campaign_products.all()}
        self.assertEqual(modes, {"One": ("INCLUDE", "EXCLUDE"), "Two": ("EXCLUDE", "INCLUDE"), "Three": ("INHERIT", "INHERIT")})
        loaded = self.staff.get(reverse("campaign_edit", args=[c.id])).context["form_data"]
        self.assertTrue(loaded["include_product_gifts"] and loaded["include_offers"])
        self.assertEqual({x["name"]: (x["row"]["gift_mode"], x["row"]["offer_mode"]) for x in loaded["products"]}, modes)

    def test_both_switches_default_to_off(self):
        body = self.ok(self.save(payload()))
        c = Campaign.objects.get(pk=body["id"])
        self.assertFalse(c.include_product_gifts)
        self.assertFalse(c.include_offers)

    def test_switching_them_off_again_is_saved(self):
        body = self.ok(self.save(payload(include_product_gifts="1", include_offers="1")))
        self.ok(self.save(payload(id=body["id"], include_product_gifts="0", include_offers="0", title="again")))
        c = Campaign.objects.get(pk=body["id"])
        self.assertFalse(c.include_product_gifts or c.include_offers)

    def test_invalid_mode_falls_back_to_inherit(self):
        p = sellable()
        body = self.ok(self.save(payload([row(p, gift_mode="HACK", offer_mode="")])))
        cp = CampaignProduct.objects.get(campaign_id=body["id"])
        self.assertEqual((cp.gift_mode, cp.offer_mode), ("INHERIT", "INHERIT"))

    def test_the_form_page_has_the_helper_text_and_dropdown_labels(self):
        html = self.staff.get(reverse("campaign_add")).content.decode()
        self.assertIn("campaign items get no free gift", html)
        self.assertIn("Use campaign setting", html)          # dropdown label (rendered by the page script)
        self.assertIn("Include", html)
        self.assertIn("Exclude", html)


# ==========================================================================
# PER-VARIANT DISCOUNTS, DELIVERY, PER-PRODUCT DELIVERY
# ==========================================================================
class VariantAndDeliveryTests(DashboardBase):
    def variant_product(self):
        p = sellable(price=0, name="Frame")
        return p, make_variant(p, price=1000, default=True), make_variant(p, price=2000)

    def test_per_variant_rows_are_saved_and_blank_ones_are_skipped(self):
        p, v1, v2 = self.variant_product()
        body = self.ok(self.save(payload([row(p, variant_mode="PER_VARIANT", variants=[
            {"variant_id": v1.id, "discount_type": "PERCENT", "discount_value": "10"},
            {"variant_id": v2.id, "discount_type": "FIXED", "discount_value": ""},
        ])])))
        cp = CampaignProduct.objects.get(campaign_id=body["id"])
        self.assertEqual(cp.variant_mode, "PER_VARIANT")
        self.assertEqual([(vd.variant_id, vd.discount_type, str(vd.discount_value)) for vd in cp.variant_discounts.all()],
                         [(v1.id, "PERCENT", "10.00")])
        self.assertTrue(any("no campaign discount" in w for w in body["warnings"][0]["problems"]))

    def test_per_variant_needs_one_valid_discount(self):
        p, v1, v2 = self.variant_product()
        self.assertIn("at least one variant", self.errors_text(self.save(payload([row(p, variant_mode="PER_VARIANT", variants=[])]))))
        text = self.errors_text(self.save(payload([row(p, variant_mode="PER_VARIANT", variants=[
            {"variant_id": v1.id, "discount_type": "PERCENT", "discount_value": "100"}])])))
        self.assertIn("Frame", text)

    def test_variant_of_another_product_is_refused(self):
        p, v1, v2 = self.variant_product()
        other_variant = make_variant(sellable(price=0, name="Other"), price=500, default=True)
        self.assertIn("variant row is not valid", self.errors_text(self.save(payload([row(p, variant_mode="PER_VARIANT", variants=[
            {"variant_id": other_variant.id, "discount_type": "PERCENT", "discount_value": "10"}])]))))

    def test_switching_back_to_all_same_removes_the_variant_rows(self):
        p, v1, v2 = self.variant_product()
        body = self.ok(self.save(payload([row(p, variant_mode="PER_VARIANT", variants=[
            {"variant_id": v1.id, "discount_type": "PERCENT", "discount_value": "10"}])])))
        self.ok(self.save(payload([row(p, variant_mode="ALL_SAME")], id=body["id"], title="again")))
        self.assertEqual(CampaignProductVariant.objects.count(), 0)

    def test_custom_delivery_is_saved_with_district_amounts(self):
        body = self.ok(self.save(payload(
            delivery_mode="CUSTOM", delivery_amount_source="SAME_FOR_ALL", delivery_basis="PER_PRODUCT",
            mixed_cart_delivery="SEPARATE", delivery_config={"Dhaka": 60, "all": 100})))
        c = Campaign.objects.get(pk=body["id"])
        self.assertEqual((c.delivery_mode, c.delivery_amount_source, c.delivery_basis, c.mixed_cart_delivery),
                         ("CUSTOM", "SAME_FOR_ALL", "PER_PRODUCT", "SEPARATE"))
        self.assertEqual(c.delivery_config, {"Dhaka": 60, "all": 100})

    def test_custom_same_for_all_needs_an_amount(self):
        text = self.errors_text(self.save(payload(delivery_mode="CUSTOM", delivery_amount_source="SAME_FOR_ALL", delivery_config={})))
        self.assertIn("delivery amount", text.lower())
        self.ok(self.save(payload(delivery_mode="CUSTOM", delivery_amount_source="PRODUCT_WISE", delivery_config={})))

    def test_delivery_amounts_must_be_valid(self):
        self.fail(self.save(payload(delivery_mode="CUSTOM", delivery_config={"all": -5})))
        self.fail(self.save(payload(delivery_mode="CUSTOM", delivery_config="not json")))
        self.fail(self.save(payload(delivery_mode="CUSTOM", delivery_config={"Dhaka": "abc"})))

    def test_per_product_delivery_amount_is_saved(self):
        p = sellable()
        body = self.ok(self.save(payload([row(p, delivery_config={"all": 50})], delivery_mode="CUSTOM",
                                         delivery_amount_source="PRODUCT_WISE", delivery_config={"all": 80})))
        self.assertEqual(CampaignProduct.objects.get(campaign_id=body["id"]).delivery_config, {"all": 50})
        self.fail(self.save(payload([row(p, delivery_config={"all": -1})])))

    def test_normal_delivery_keeps_the_site_wide_rules(self):
        body = self.ok(self.save(payload(delivery_mode="NORMAL")))
        self.assertEqual(Campaign.objects.get(pk=body["id"]).delivery_mode, "NORMAL")


# ==========================================================================
# OVERLAP RULE (SPEC 5)
# ==========================================================================
class OverlapTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.p = sellable(name="Shared Cradle")
        self.q = sellable(name="Second Chair")
        now = timezone.now()
        self.first = make_campaign(title="Black Friday", start=now + timedelta(hours=1), end=now + timedelta(days=3))
        add(self.first, self.p)
        add(self.first, self.q)

    def overlapping(self, products, **over):
        now = timezone.now()
        return payload(products, start_at=local(now + timedelta(days=1)), end_at=local(now + timedelta(days=5)),
                       publish="1", **over)

    def test_the_error_names_the_conflicting_campaign_and_the_products(self):
        text = self.errors_text(self.save(self.overlapping([row(self.p), row(self.q)])))
        self.assertIn("Black Friday", text)
        self.assertIn("Shared Cradle", text)
        self.assertIn("Second Chair", text)
        self.assertEqual(Campaign.objects.count(), 1)

    def test_the_response_carries_the_conflict_list_for_the_page(self):
        body = self.fail(self.save(self.overlapping([row(self.p)])))
        self.assertEqual(body["conflicts"], [{"campaign": "Black Friday", "product": "Shared Cradle"}])

    def test_different_dates_do_not_conflict(self):
        now = timezone.now()
        later = payload([row(self.p)], start_at=local(now + timedelta(days=10)), end_at=local(now + timedelta(days=12)), publish="1")
        self.ok(self.save(later))

    def test_allowed_only_when_both_campaigns_allow_it(self):
        Campaign.objects.filter(pk=self.first.pk).update(allow_overlap=True)
        self.fail(self.save(self.overlapping([row(self.p)])))                                   # the new one does not allow
        self.ok(self.save(self.overlapping([row(self.p)], allow_overlap="1", title="Cyber Monday")))   # both do

    def test_a_draft_is_saved_without_the_overlap_check(self):
        now = timezone.now()
        draft = payload([row(self.p)], start_at=local(now + timedelta(days=1)), end_at=local(now + timedelta(days=5)), publish="0")
        body = self.ok(self.save(draft))
        self.assertFalse(Campaign.objects.get(pk=body["id"]).is_active)

    def test_resuming_a_draft_runs_the_same_check(self):
        now = timezone.now()
        body = self.ok(self.save(payload([row(self.p)], start_at=local(now + timedelta(days=1)),
                                         end_at=local(now + timedelta(days=5)), publish="0")))
        res = self.staff.post(reverse("campaign_toggle", args=[body["id"]]))
        self.assertEqual(res.status_code, 400)
        self.assertIn("Black Friday", res.json()["message"])
        self.assertFalse(Campaign.objects.get(pk=body["id"]).is_active)

    def test_editing_the_first_campaign_does_not_conflict_with_itself(self):
        self.ok(self.save(payload([row(self.p), row(self.q)], id=self.first.id, title="Black Friday", publish="1",
                                  start_at=local(self.first.start_at), end_at=local(self.first.end_at))))


# ==========================================================================
# PAUSE / RESUME / DUPLICATE / DELETE
# ==========================================================================
class ActionTests(DashboardBase):
    def test_pause_and_resume(self):
        c = make_campaign()
        add(c, sellable())
        res = self.staff.post(reverse("campaign_toggle", args=[c.id]))
        self.assertEqual((res.json()["is_active"], res.json()["campaign_status"]), (False, "draft"))
        c.refresh_from_db()
        self.assertFalse(c.is_active)
        res = self.staff.post(reverse("campaign_toggle", args=[c.id]))
        self.assertEqual((res.json()["is_active"], res.json()["campaign_status"]), (True, "live"))

    def test_resume_needs_a_product(self):
        c = make_campaign(is_active=False)
        res = self.staff.post(reverse("campaign_toggle", args=[c.id]))
        self.assertEqual(res.status_code, 400)
        self.assertIn("at least one product", res.json()["message"])

    def test_pausing_a_campaign_stops_its_public_page(self):
        c = make_campaign(title="Public One")
        add(c, sellable())
        self.assertEqual(Client().get("/api/ecom/campaigns/public-one/").status_code, 200)
        self.staff.post(reverse("campaign_toggle", args=[c.id]))
        self.assertEqual(Client().get("/api/ecom/campaigns/public-one/").status_code, 404)

    def test_duplicate_makes_a_draft_copy_with_products_variants_and_its_own_files(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(MEDIA_ROOT=media):
            p = sellable(price=0, name="Frame")
            v1, v2 = make_variant(p, price=1000, default=True), make_variant(p, price=2000)
            c = make_campaign(title="Original", include_offers=True, allow_coupon=True)
            c.thumbnail.save("thumb.png", png(), save=True)
            cp = add(c, p, "PERCENT", 10, variant_mode="PER_VARIANT", stock_limit=5, gift_mode="INCLUDE")
            CampaignProductVariant.objects.create(campaign_product=cp, variant=v1, discount_type="PERCENT", discount_value=12)

            res = self.staff.post(reverse("campaign_duplicate", args=[c.id]))
            copy = Campaign.objects.get(pk=res.json()["id"])
            self.assertFalse(copy.is_active)
            self.assertEqual((copy.title, copy.include_offers, copy.allow_coupon), ("Original (Copy)", True, True))
            self.assertNotEqual(copy.slug, c.slug)
            copied = copy.campaign_products.get()
            self.assertEqual((copied.stock_limit, copied.gift_mode, copied.variant_mode), (5, "INCLUDE", "PER_VARIANT"))
            self.assertEqual(copied.variant_discounts.get().discount_value, 12)
            self.assertEqual(c.campaign_products.count(), 1)                 # the original is untouched
            self.assertNotEqual(copy.thumbnail.name, c.thumbnail.name)       # its OWN file ...
            self.assertTrue(copy.thumbnail.storage.exists(copy.thumbnail.name))
            self.staff.post(reverse("campaign_delete", args=[copy.id]))      # ... so deleting the copy keeps the original's
            self.assertTrue(c.thumbnail.storage.exists(c.thumbnail.name))

    def test_delete_removes_the_campaign_its_rows_and_files(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(MEDIA_ROOT=media):
            c = make_campaign()
            c.banner_desktop.save("b.png", png(), save=True)
            add(c, sellable())
            path = c.banner_desktop.path
            res = self.staff.post(reverse("campaign_delete", args=[c.id]))
            self.assertTrue(res.json()["status"])
            self.assertFalse(Campaign.objects.filter(pk=c.pk).exists())
            self.assertEqual(CampaignProduct.objects.count(), 0)
            import os
            self.assertFalse(os.path.exists(path))

    def test_the_list_has_a_delete_confirmation_and_all_actions(self):
        make_campaign(title="Has Actions")
        html = self.staff.get(reverse("campaign_list")).content.decode()
        for text in ("cpxDeleteModal", "CampaignListUI.duplicate", "CampaignListUI.toggle", "CampaignListUI.remove", "Create Campaign"):
            self.assertIn(text, html, text)

    def test_actions_on_a_missing_campaign_are_404(self):
        for name in ("campaign_toggle", "campaign_duplicate", "campaign_delete"):
            self.assertEqual(self.staff.post(reverse(name, args=[12345])).status_code, 404, name)


# ==========================================================================
# IMAGES
# ==========================================================================
class ImageTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_images_are_uploaded_and_replaced_and_old_files_removed(self):
        import os
        body = self.ok(self.save(payload(), thumbnail=png("t.png"), banner_desktop=png("d.png"), banner_mobile=png("m.png")))
        c = Campaign.objects.get(pk=body["id"])
        old_thumb = c.thumbnail.path
        self.assertTrue(all(os.path.exists(f.path) for f in (c.thumbnail, c.banner_desktop, c.banner_mobile)))
        self.ok(self.save(payload(id=c.id, title="replaced"), thumbnail=png("t2.png", color="blue")))
        c.refresh_from_db()
        self.assertFalse(os.path.exists(old_thumb))
        self.assertTrue(os.path.exists(c.thumbnail.path))
        self.assertTrue(c.banner_desktop)                                   # not uploaded again = kept

    def test_an_image_can_be_cleared(self):
        import os
        body = self.ok(self.save(payload(), banner_mobile=png("m.png")))
        c = Campaign.objects.get(pk=body["id"])
        path = c.banner_mobile.path
        self.ok(self.save(payload(id=c.id, title="cleared", clear_banner_mobile="1")))
        c.refresh_from_db()
        self.assertFalse(c.banner_mobile)
        self.assertFalse(os.path.exists(path))

    def test_a_file_that_is_not_an_image_is_refused(self):
        fake = SimpleUploadedFile("evil.png", b"<?php echo 1;", content_type="image/png")
        text = self.errors_text(self.save(payload(), thumbnail=fake))
        self.assertIn("not a valid image", text)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_very_wide_banners_are_shrunk_without_cropping(self):
        body = self.ok(self.save(payload(), banner_desktop=png("wide.png", size=(4000, 1000))))
        c = Campaign.objects.get(pk=body["id"])
        self.assertEqual((c.banner_desktop.width, c.banner_desktop.height), (2000, 500))


# ==========================================================================
# PRODUCT PICKER
# ==========================================================================
class ProductSearchTests(DashboardBase):
    def search(self, **params):
        res = self.staff.get(reverse("campaign_product_search"), params)
        self.assertEqual(res.status_code, 200)
        return res.json()["products"]

    def test_search_by_name_sku_and_category(self):
        cat = Category.objects.create(name="Cradles")
        a = sellable(name="Wooden Cradle", category=cat, sku="CR-001")
        b = sellable(name="Pencil Box", sku="PB-77")
        self.assertEqual([p["id"] for p in self.search(q="wooden")], [a.id])
        self.assertEqual([p["id"] for p in self.search(q="PB-77")], [b.id])
        self.assertEqual([p["id"] for p in self.search(q="cradles")], [a.id])
        self.assertEqual({p["id"] for p in self.search(q="")}, {a.id, b.id})
        self.assertEqual(self.search(q="zzz"), [])

    def test_only_active_sellable_products_and_exclude_works(self):
        a = sellable(name="Visible One")
        make_product(name="Hidden Draft", status="Draft")
        make_product(name="Gift Only Thing", is_gift_only=True)
        b = sellable(name="Visible Two")
        self.assertEqual({p["id"] for p in self.search()}, {a.id, b.id})
        self.assertEqual([p["id"] for p in self.search(exclude=str(a.id))], [b.id])

    def test_cards_carry_prices_variants_and_the_gift_and_offer_chips(self):
        p = sellable(price=1000, discount=800, name="Chips")
        make_gift_for(p)
        offer = Offer.objects.create(name="Buy 2 Get 1", apply_to_all=True)
        OfferTier.objects.create(offer=offer, buy_qty=2, free_qty=1)
        card = self.search(q="Chips")[0]
        self.assertEqual((card["price"], card["discount_price"]), (1000, 800))
        self.assertTrue(card["has_gift"])
        self.assertEqual(card["offers"], ["Buy 2 Get 1"])
        plain = sellable(name="Plain Chair")
        Offer.objects.all().delete()
        card = self.search(q="Plain")[0]
        self.assertFalse(card["has_gift"])
        self.assertEqual(card["offers"], [])

    def test_variant_products_list_their_active_variants(self):
        p = sellable(price=0, name="Frame")
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000, discount=1800)
        make_variant(p, price=999)
        from product.models import ProductVariant
        ProductVariant.objects.filter(pk=v1.pk + 2).update(is_active=False)
        card = self.search(q="Frame")[0]
        self.assertTrue(card["has_variants"])
        self.assertEqual([v["price"] for v in card["variants"]], [1000, 2000])
        self.assertEqual(card["display_variant_id"], v1.id)

    def test_search_needs_a_staff_login(self):
        self.assertEqual(Client().get(reverse("campaign_product_search")).status_code, 302)


# ==========================================================================
# PREVIEW FORMULAS: the JavaScript on the page must give the Python answer
# ==========================================================================
class PreviewFormulaParityTests(TestCase):
    def test_javascript_preview_matches_resolve_line_price(self):
        import re
        import random
        import subprocess
        from decimal import Decimal
        from pathlib import Path
        from types import SimpleNamespace as NS

        from django.conf import settings

        from campaigns.pricing import resolve_line_price

        if shutil.which("node") is None:
            self.skipTest("node is not installed")
        script = (Path(settings.BASE_DIR) / "dashbaord/templates/db_campaign/partial/campaign_form_script.html").read_text(encoding="utf-8")
        block = re.search(r"/\* PRICE-FORMULAS-START \*/(.*?)/\* PRICE-FORMULAS-END \*/", script, re.S).group(1)

        rnd = random.Random(11)
        cases = []
        for _ in range(600):
            regular = rnd.choice([0, 1, 50, 99, 333, 1000, 1005, 1299, 7980])
            cases.append({
                "regular": regular, "own": rnd.choice([0, 0, regular // 2, regular + 5]),
                "dtype": rnd.choice(["PERCENT", "FIXED"]),
                "value": rnd.choice([0, 1, 10, 12.5, 15, 33, 50, 99.5, 100, 500, 10000]),
                "cfg": {"discount_base": rnd.choice(["REGULAR", "CURRENT"]), "strike_price_display": rnd.choice(["REGULAR", "CURRENT"]),
                        "badge_mode": rnd.choice(["DISCOUNT_ONLY", "NAME_AND_DISCOUNT"]), "badge_label": rnd.choice(["", "Black Friday"]),
                        "title": "Eid Sale"},
            })
        node_src = block + """
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify(cases.map(c => { const r = resolveLine(c.cfg, c.regular, c.own, {type: c.dtype, value: c.value}, 'no_value');
  return {price: r.price, strike: r.strike, savings: r.savings, percent: r.percent, badge: r.badge, visible: r.visible}; })));
"""
        out = subprocess.run(["node", "-e", node_src], input=json.dumps(cases), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        js = json.loads(out.stdout)
        for case, got in zip(cases, js):
            campaign = NS(**case["cfg"])
            campaign.badge_label = case["cfg"]["badge_label"] or case["cfg"]["title"][:20]
            cp = NS(variant_mode="ALL_SAME", discount_type=case["dtype"], discount_value=Decimal(str(case["value"])),
                    variant_discounts=NS(all=lambda: []))
            product = NS(has_variants=False, price=Decimal(case["regular"]), discount_price=Decimal(case["own"]))
            r = resolve_line_price(campaign, cp, product)
            expected = {"price": int(r.campaign_price), "strike": None if r.strike is None else int(r.strike),
                        "savings": int(r.savings_amount), "percent": r.savings_percent, "badge": r.badge_text,
                        "visible": r.has_visible_discount}
            self.assertEqual(got, expected, case)
