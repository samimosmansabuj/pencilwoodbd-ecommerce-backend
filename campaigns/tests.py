"""
Tests for the campaigns app (Task 1): status, overlap, price rules, gifts/offers switches, public APIs.
Run:  python manage.py test campaigns
"""
import itertools
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from offers.models import Offer, OfferTier, ProductComboPair
from pencilwoodbd.choices import (
    CAMPAIGN_BADGE_MODE as BADGE,
    CAMPAIGN_DISCOUNT_TYPE as DT,
    CAMPAIGN_PRICE_SOURCE as SRC,
    CAMPAIGN_STATUS as ST,
    CAMPAIGN_SWITCH_MODE as SW,
    CAMPAIGN_VARIANT_MODE as VM,
    CATEGORY_PRODUCT_STATUS,
    PRODUCT_GIFT_TYPE,
)
from product.models import Product, ProductGifting, ProductVariant

from .models import Campaign, CampaignProduct, CampaignProductVariant
from .pricing import (
    WARN_ABOVE_CURRENT_PRICE,
    WARN_NO_VISIBLE_DISCOUNT,
    WARN_VARIANT_DISCOUNT_MISSING,
    build_campaign_pricing,
    effective_switches,
    find_overlap_conflicts,
    get_campaign_status,
    get_sold_units_map,
    resolve_line_price,
    round_half_up,
    stock_left_for,
    validate_no_overlap,
)

_counter = itertools.count(1)


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------
def make_product(price=1000, discount=0, name=None, **kw):
    name = name or f"Test Product {next(_counter)}"
    kw.setdefault("status", CATEGORY_PRODUCT_STATUS.ACTIVE)
    return Product.objects.create(name=name, price=price, discount_price=discount, **kw)


def make_variant(product, price=1000, discount=0, default=False, qty=10, **attrs):
    v = ProductVariant.objects.create(
        product=product, price=price, discount_price=discount, is_default=default,
        inventory_quantity=qty, attributes=attrs or {"size": f"S{next(_counter)}"},
    )
    product.refresh_from_db()
    return v


def make_campaign(title=None, start=None, end=None, **kw):
    now = timezone.now()
    kw.setdefault("is_active", True)
    return Campaign.objects.create(
        title=title or f"Campaign {next(_counter)}",
        start_at=start or now - timedelta(hours=1),
        end_at=end or now + timedelta(days=1),
        **kw,
    )


def add(campaign, product, discount_type=DT.PERCENT, value=20, **kw):
    return CampaignProduct.objects.create(
        campaign=campaign, product=product, discount_type=discount_type, discount_value=value, **kw
    )


def fresh(product):
    """Re-read a product so cached/prefetched relations are current."""
    return Product.objects.prefetch_related("variants").get(pk=product.pk)


def line(campaign, cp, product, variant=None):
    cp = CampaignProduct.objects.prefetch_related("variant_discounts").get(pk=cp.pk)
    return resolve_line_price(campaign, cp, fresh(product), variant)


# ==========================================================================
# MODELS / VALIDATION
# ==========================================================================
class CampaignModelTests(TestCase):
    def test_slug_auto_from_title_and_unique(self):
        a = make_campaign(title="Black Friday")
        b = make_campaign(title="Black Friday")
        self.assertEqual(a.slug, "black-friday")
        self.assertEqual(b.slug, "black-friday-1")

    def test_slug_is_stable_when_title_changes(self):
        c = make_campaign(title="Eid Sale")
        c.title = "Eid Mega Sale"
        c.save()
        self.assertEqual(c.slug, "eid-sale")

    def test_bangla_only_title_still_gets_a_slug(self):
        c = make_campaign(title="ঈদ সেল")
        self.assertEqual(c.slug, "campaign")

    def test_badge_label_defaults_to_title_max_20(self):
        self.assertEqual(make_campaign(title="Black Friday").badge_label, "Black Friday")
        long = make_campaign(title="A very long campaign title indeed")
        self.assertEqual(long.badge_label, "A very long campaign")
        self.assertEqual(len(long.badge_label), 20)
        custom = make_campaign(title="Black Friday", badge_label="BF")
        self.assertEqual(custom.badge_label, "BF")

    def test_defaults(self):
        c = make_campaign()
        self.assertEqual((c.discount_base, c.strike_price_display), (SRC.CURRENT, SRC.CURRENT))
        self.assertFalse(c.allow_overlap)
        self.assertFalse(c.allow_coupon)
        self.assertFalse(c.include_product_gifts)
        self.assertFalse(c.include_offers)

    def test_end_must_be_after_start(self):
        now = timezone.now()
        c = Campaign(title="x", start_at=now, end_at=now)
        with self.assertRaises(ValidationError) as ctx:
            c.full_clean()
        self.assertIn("end_at", ctx.exception.message_dict)
        # and the database enforces it too
        with self.assertRaises(IntegrityError), transaction.atomic():
            Campaign.objects.create(title="bad", start_at=now, end_at=now - timedelta(hours=1))

    def test_percent_must_be_between_0_and_100_exclusive(self):
        c = make_campaign()
        p = make_product()
        for bad in (0, -5, 100, 150):
            cp = CampaignProduct(campaign=c, product=p, discount_type=DT.PERCENT, discount_value=bad)
            with self.assertRaises(ValidationError, msg=f"percent {bad}"):
                cp.full_clean()
        for good in (Decimal("0.01"), 20, Decimal("99.99")):
            CampaignProduct(campaign=c, product=p, discount_type=DT.PERCENT, discount_value=good).full_clean()

    def test_fixed_must_be_positive(self):
        c = make_campaign()
        p = make_product()
        for bad in (0, -1):
            with self.assertRaises(ValidationError):
                CampaignProduct(campaign=c, product=p, discount_type=DT.FIXED, discount_value=bad).full_clean()
        CampaignProduct(campaign=c, product=p, discount_type=DT.FIXED, discount_value=1).full_clean()

    def test_per_variant_mode_does_not_require_row_level_value(self):
        c = make_campaign()
        p = make_product()
        CampaignProduct(campaign=c, product=p, variant_mode=VM.PER_VARIANT, discount_value=0).full_clean()

    def test_variant_row_validation_and_db_constraint(self):
        c = make_campaign()
        p = make_product()
        v = make_variant(p)
        other_v = make_variant(make_product())
        cp = add(c, p, variant_mode=VM.PER_VARIANT)
        with self.assertRaises(ValidationError):
            CampaignProductVariant(campaign_product=cp, variant=v, discount_type=DT.PERCENT, discount_value=100).full_clean()
        with self.assertRaises(ValidationError):  # variant of another product
            CampaignProductVariant(campaign_product=cp, variant=other_v, discount_type=DT.FIXED, discount_value=5).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampaignProductVariant.objects.create(campaign_product=cp, variant=v, discount_type=DT.PERCENT, discount_value=0)

    def test_unique_product_per_campaign(self):
        c = make_campaign()
        p = make_product()
        add(c, p)
        with self.assertRaises(IntegrityError), transaction.atomic():
            add(c, p)

    def test_delivery_config_validation(self):
        c = make_campaign()
        for bad in ([], "x", {"all": -1}, {"all": "abc"}, {"": 10}):
            c.delivery_config = bad
            with self.assertRaises(ValidationError, msg=repr(bad)):
                c.full_clean()
        for good in ({"all": 80}, {"Dhaka": 60, "all": 100}, {}):
            c.delivery_config = good
            c.full_clean()

    def test_custom_same_for_all_delivery_needs_config(self):
        c = make_campaign(delivery_mode="CUSTOM", delivery_amount_source="SAME_FOR_ALL", delivery_config={})
        with self.assertRaises(ValidationError) as ctx:
            c.full_clean()
        self.assertIn("delivery_config", ctx.exception.message_dict)

    def test_gift_only_product_cannot_join(self):
        c = make_campaign()
        gift = make_product(is_gift_only=True)
        with self.assertRaises(ValidationError):
            CampaignProduct(campaign=c, product=gift, discount_type=DT.PERCENT, discount_value=10).full_clean()


# ==========================================================================
# STATUS (SPEC 2)
# ==========================================================================
class StatusTests(TestCase):
    def setUp(self):
        self.start = timezone.now().replace(microsecond=0)
        self.end = self.start + timedelta(days=2)

    def campaign(self, **kw):
        return Campaign(title="s", start_at=self.start, end_at=self.end, **kw)

    def test_draft_when_not_active_whatever_the_dates(self):
        c = self.campaign(is_active=False)
        for when in (self.start - timedelta(days=1), self.start + timedelta(hours=1), self.end + timedelta(days=1)):
            self.assertEqual(get_campaign_status(c, when), ST.DRAFT)

    def test_upcoming_live_ended(self):
        c = self.campaign(is_active=True)
        self.assertEqual(get_campaign_status(c, self.start - timedelta(seconds=1)), ST.UPCOMING)
        self.assertEqual(get_campaign_status(c, self.start + timedelta(hours=5)), ST.LIVE)
        self.assertEqual(get_campaign_status(c, self.end + timedelta(seconds=1)), ST.ENDED)

    def test_boundaries_are_inclusive(self):
        c = self.campaign(is_active=True)
        self.assertEqual(get_campaign_status(c, self.start), ST.LIVE)
        self.assertEqual(get_campaign_status(c, self.end), ST.LIVE)

    def test_model_property_uses_server_clock(self):
        live = make_campaign()
        self.assertEqual(live.status, ST.LIVE)
        now = timezone.now()
        self.assertEqual(make_campaign(start=now + timedelta(hours=1), end=now + timedelta(hours=2)).status, ST.UPCOMING)
        self.assertEqual(make_campaign(start=now - timedelta(hours=2), end=now - timedelta(hours=1)).status, ST.ENDED)
        self.assertEqual(make_campaign(is_active=False).status, ST.DRAFT)


# ==========================================================================
# OVERLAP (SPEC 5)
# ==========================================================================
class OverlapTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.p = make_product(name="Shared Product")

    def window(self, start_h, end_h):
        return dict(start=self.now + timedelta(hours=start_h), end=self.now + timedelta(hours=end_h))

    def test_overlapping_windows_conflict_and_name_the_other_campaign(self):
        a = make_campaign(title="Black Friday", **self.window(0, 48))
        add(a, self.p)
        b = make_campaign(title="Cyber Monday", **self.window(24, 72))
        conflicts = find_overlap_conflicts(b, [self.p.id])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["campaign_title"], "Black Friday")
        self.assertEqual(conflicts[0]["product_name"], "Shared Product")
        with self.assertRaises(ValidationError) as ctx:
            validate_no_overlap(b, [self.p.id])
        self.assertIn("Black Friday", " ".join(ctx.exception.messages))

    def test_non_overlapping_windows_are_fine(self):
        add(make_campaign(**self.window(0, 24)), self.p)
        later = make_campaign(**self.window(25, 48))
        self.assertEqual(find_overlap_conflicts(later, [self.p.id]), [])

    def test_touching_windows_overlap_because_boundaries_are_inclusive(self):
        add(make_campaign(**self.window(0, 24)), self.p)
        touching = make_campaign(**self.window(24, 48))
        self.assertEqual(len(find_overlap_conflicts(touching, [self.p.id])), 1)

    def test_overlap_allowed_only_when_BOTH_allow_it(self):
        for a_allows, b_allows, expect_conflict in [(True, True, False), (True, False, True), (False, True, True), (False, False, True)]:
            with self.subTest(a=a_allows, b=b_allows):
                Campaign.objects.all().delete()
                a = make_campaign(allow_overlap=a_allows, **self.window(0, 48))
                add(a, self.p)
                b = make_campaign(allow_overlap=b_allows, **self.window(10, 60))
                self.assertEqual(bool(find_overlap_conflicts(b, [self.p.id])), expect_conflict)

    def test_different_products_never_conflict(self):
        add(make_campaign(**self.window(0, 48)), self.p)
        b = make_campaign(**self.window(0, 48))
        self.assertEqual(find_overlap_conflicts(b, [make_product().id]), [])

    def test_a_campaign_does_not_conflict_with_itself(self):
        a = make_campaign(**self.window(0, 48))
        add(a, self.p)
        self.assertEqual(find_overlap_conflicts(a), [])

    def test_draft_campaigns_neither_block_nor_are_blocked(self):
        add(make_campaign(is_active=False, **self.window(0, 48)), self.p)
        live = make_campaign(**self.window(0, 48))
        self.assertEqual(find_overlap_conflicts(live, [self.p.id]), [])       # draft does not block
        draft = make_campaign(is_active=False, **self.window(0, 48))
        add(make_campaign(**self.window(0, 48)), self.p)
        self.assertEqual(find_overlap_conflicts(draft, [self.p.id]), [])       # draft is not checked...
        draft.is_active = True                                                  # ...until it is switched on
        self.assertEqual(len(find_overlap_conflicts(draft, [self.p.id])), 1)

    def test_product_switched_off_inside_a_campaign_is_ignored(self):
        add(make_campaign(**self.window(0, 48)), self.p, is_active=False)
        self.assertEqual(find_overlap_conflicts(make_campaign(**self.window(0, 48)), [self.p.id]), [])

    def test_in_memory_date_edits_are_checked_before_saving(self):
        a = make_campaign(title="A", **self.window(0, 24))
        add(a, self.p)
        b = make_campaign(title="B", **self.window(100, 124))
        add(b, make_product())
        b.start_at, b.end_at = self.now, self.now + timedelta(hours=12)       # NOT saved
        self.assertEqual(len(find_overlap_conflicts(b, [self.p.id])), 1)

    def test_model_clean_blocks_conflicting_row(self):
        add(make_campaign(title="Black Friday", **self.window(0, 48)), self.p)
        other = make_campaign(**self.window(10, 20))
        row = CampaignProduct(campaign=other, product=self.p, discount_type=DT.PERCENT, discount_value=10)
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn("Black Friday", str(ctx.exception))


# ==========================================================================
# PRICE RULES (SPEC 3)
# ==========================================================================
class PriceRuleTests(TestCase):
    def test_round_half_up(self):
        self.assertEqual(round_half_up("42.5"), Decimal("43"))
        self.assertEqual(round_half_up("42.49"), Decimal("42"))
        self.assertEqual(round_half_up("0.5"), Decimal("1"))
        self.assertEqual(round_half_up("2.5"), Decimal("3"))   # Python's round() would give 2

    def test_percent_simple_product_without_own_discount(self):
        p = make_product(price=1000)
        c = make_campaign()
        r = line(c, add(c, p, DT.PERCENT, 20), p)
        self.assertEqual((r.regular, r.current, r.base), (1000, 1000, 1000))
        self.assertEqual(r.campaign_price, 800)
        self.assertEqual(r.strike, 1000)
        self.assertEqual((r.savings_amount, r.savings_percent), (200, 20))
        self.assertEqual(r.badge_text, "20% OFF")
        self.assertTrue(r.has_visible_discount)
        self.assertEqual(r.warnings, [])

    def test_fixed_simple_product(self):
        p = make_product(price=1000)
        c = make_campaign()
        r = line(c, add(c, p, DT.FIXED, 150), p)
        self.assertEqual(r.campaign_price, 850)
        self.assertEqual((r.savings_amount, r.savings_percent), (150, 15))
        self.assertEqual(r.badge_text, "৳150 OFF")

    def test_product_with_own_discount_price_current_vs_regular(self):
        p = make_product(price=1000, discount=800)
        c = make_campaign()
        cp = add(c, p, DT.PERCENT, 10)
        r = line(c, cp, p)
        self.assertEqual((r.regular, r.current), (1000, 800))

    def test_default_campaign_never_charges_more_than_the_normal_price(self):
        # real-data case: regular 7980, already discounted to 3990 -> a 20% campaign must give 3192, not 6384
        p = make_product(price=7980, discount=3990)
        c = make_campaign()
        r = line(c, add(c, p, DT.PERCENT, 20), p)
        self.assertEqual(r.campaign_price, 3192)
        self.assertEqual((r.strike, r.badge_text), (3990, "20% OFF"))
        self.assertNotIn(WARN_ABOVE_CURRENT_PRICE, r.warnings)

    def test_discount_base_REGULAR(self):
        p = make_product(price=1000, discount=800)
        c = make_campaign(discount_base=SRC.REGULAR, strike_price_display=SRC.REGULAR)
        r = line(c, add(c, p, DT.PERCENT, 25), p)
        self.assertEqual(r.base, 1000)
        self.assertEqual(r.campaign_price, 750)      # 25% of 1000

    def test_discount_base_CURRENT(self):
        p = make_product(price=1000, discount=800)
        c = make_campaign(discount_base=SRC.CURRENT, strike_price_display=SRC.REGULAR)
        r = line(c, add(c, p, DT.PERCENT, 25), p)
        self.assertEqual(r.base, 800)
        self.assertEqual(r.campaign_price, 600)      # 25% of 800

    def test_discount_base_CURRENT_without_own_discount_falls_back_to_regular(self):
        p = make_product(price=1000)
        c = make_campaign(discount_base=SRC.CURRENT)
        r = line(c, add(c, p, DT.PERCENT, 25), p)
        self.assertEqual((r.base, r.campaign_price), (1000, 750))

    def test_strike_REGULAR_vs_CURRENT(self):
        p = make_product(price=1000, discount=800)
        for strike_src, expected_strike, savings, pct in [(SRC.REGULAR, 1000, 400, 40), (SRC.CURRENT, 800, 200, 25)]:
            with self.subTest(strike=strike_src):
                Campaign.objects.all().delete()
                c = make_campaign(discount_base=SRC.CURRENT, strike_price_display=strike_src)
                r = line(c, add(c, p, DT.PERCENT, 25), p)
                self.assertEqual(r.campaign_price, 600)
                self.assertEqual(r.strike, expected_strike)
                self.assertEqual((r.savings_amount, r.savings_percent), (savings, pct))

    def test_badge_numbers_come_from_visible_prices_not_the_configured_value(self):
        # configured 25% off the current price 800 -> final 600; strike shown is REGULAR 1000 -> badge says 40%
        p = make_product(price=1000, discount=800)
        c = make_campaign(discount_base=SRC.CURRENT, strike_price_display=SRC.REGULAR)
        r = line(c, add(c, p, DT.PERCENT, 25), p)
        self.assertEqual(r.badge_text, "40% OFF")
        # FIXED unit: 100 off the current 800 = 700, strike REGULAR 1000 -> savings 300
        Campaign.objects.all().delete()
        c = make_campaign(discount_base=SRC.CURRENT, strike_price_display=SRC.REGULAR)
        r = line(c, add(c, p, DT.FIXED, 100), p)
        self.assertEqual((r.campaign_price, r.savings_amount, r.badge_text), (700, 300, "৳300 OFF"))

    def test_rounding_half_up_on_percent(self):
        # 85% of 50 = 42.5 -> 43 ; 90% of 333 = 299.7 -> 300 ; 95% of 1005 = 954.75 -> 955
        for price, pct, expected in [(50, 15, 43), (333, 10, 300), (1005, 5, 955), (999, 33, 669)]:
            with self.subTest(price=price, pct=pct):
                Campaign.objects.all().delete()
                p = make_product(price=price)
                c = make_campaign()
                self.assertEqual(line(c, add(c, p, DT.PERCENT, pct), p).campaign_price, expected)

    def test_rounding_of_fractional_fixed_and_decimal_percent(self):
        p = make_product(price=1000)
        c = make_campaign()
        self.assertEqual(line(c, add(c, p, DT.FIXED, Decimal("99.50")), p).campaign_price, 901)   # 900.5 -> 901
        Campaign.objects.all().delete()
        c = make_campaign()
        self.assertEqual(line(c, add(c, p, DT.PERCENT, Decimal("12.5")), p).campaign_price, 875)  # 875.0

    def test_fixed_larger_than_price_clamps_to_zero(self):
        p = make_product(price=100)
        c = make_campaign()
        r = line(c, add(c, p, DT.FIXED, 500), p)
        self.assertEqual(r.campaign_price, 0)
        self.assertEqual(r.savings_amount, 100)
        self.assertEqual(r.savings_percent, 100)

    def test_campaign_price_never_negative_even_with_bad_data(self):
        p = make_product(price=100)
        c = make_campaign()
        cp = add(c, p, DT.PERCENT, 20)
        CampaignProduct.objects.filter(pk=cp.pk).update(discount_value=250)    # bypasses validation
        r = line(c, cp, p)
        self.assertEqual(r.campaign_price, 0)

    # ---- strike <= final -> no strike, no badge, dashboard warning ----
    def test_no_visible_discount_when_final_equals_strike(self):
        # regular 1000, own discount 800. Discount 20% from REGULAR = 800 = the CURRENT strike
        p = make_product(price=1000, discount=800)
        c = make_campaign(discount_base=SRC.REGULAR, strike_price_display=SRC.CURRENT)
        r = line(c, add(c, p, DT.PERCENT, 20), p)
        self.assertEqual(r.campaign_price, 800)
        self.assertIsNone(r.strike)
        self.assertIsNone(r.badge_text)
        self.assertEqual((r.savings_amount, r.savings_percent), (0, 0))
        self.assertFalse(r.has_visible_discount)
        self.assertIn(WARN_NO_VISIBLE_DISCOUNT, r.warnings)

    def test_no_visible_discount_when_final_above_strike(self):
        p = make_product(price=1000, discount=800)
        c = make_campaign(discount_base=SRC.REGULAR, strike_price_display=SRC.CURRENT)
        r = line(c, add(c, p, DT.PERCENT, 10), p)          # 900 > current 800
        self.assertEqual(r.campaign_price, 900)
        self.assertIsNone(r.strike)
        self.assertIsNone(r.badge_text)
        self.assertIn(WARN_NO_VISIBLE_DISCOUNT, r.warnings)
        self.assertIn(WARN_ABOVE_CURRENT_PRICE, r.warnings)   # customer pays MORE than the normal 800

    def test_public_object_has_null_strike_and_badge_when_not_visible(self):
        p = make_product(price=1000, discount=800)
        c = make_campaign(discount_base=SRC.REGULAR, strike_price_display=SRC.CURRENT)
        cp = add(c, p, DT.PERCENT, 20)
        pricing = build_campaign_pricing(c, CampaignProduct.objects.get(pk=cp.pk), fresh(p))
        self.assertIsNone(pricing["strike_price"])
        self.assertIsNone(pricing["badge_text"])
        self.assertEqual(pricing["savings_amount"], 0)

    # ---- every badge text mode ----
    def test_badge_text_all_modes(self):
        p = make_product(price=1000)
        cases = [
            (BADGE.DISCOUNT_ONLY, DT.PERCENT, 20, "20% OFF"),
            (BADGE.DISCOUNT_ONLY, DT.FIXED, 200, "৳200 OFF"),
            (BADGE.NAME_AND_DISCOUNT, DT.PERCENT, 20, "Black Friday · 20% OFF"),
            (BADGE.NAME_AND_DISCOUNT, DT.FIXED, 200, "Black Friday · ৳200 OFF"),
        ]
        for mode, dtype, value, expected in cases:
            with self.subTest(mode=mode, dtype=dtype):
                Campaign.objects.all().delete()
                c = make_campaign(title="Black Friday", badge_mode=mode)
                self.assertEqual(line(c, add(c, p, dtype, value), p).badge_text, expected)

    def test_badge_name_uses_custom_label_and_default_label(self):
        p = make_product(price=1000)
        c = make_campaign(title="Black Friday Mega Sale 2026", badge_mode=BADGE.NAME_AND_DISCOUNT)
        self.assertEqual(c.badge_label, "Black Friday Mega Sa")      # default = title cut to 20
        self.assertEqual(line(c, add(c, p, DT.PERCENT, 10), p).badge_text, "Black Friday Mega Sa · 10% OFF")
        Campaign.objects.all().delete()
        c = make_campaign(title="Black Friday", badge_mode=BADGE.NAME_AND_DISCOUNT, badge_label="BF")
        self.assertEqual(line(c, add(c, p, DT.PERCENT, 10), p).badge_text, "BF · 10% OFF")

    # ---- variants ----
    def test_variants_ALL_SAME_uses_each_variants_own_prices(self):
        p = make_product(price=0)
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000, discount=1800)
        c = make_campaign(discount_base=SRC.REGULAR)
        cp = add(c, p, DT.PERCENT, 10, variant_mode=VM.ALL_SAME)
        r1, r2 = line(c, cp, p, v1), line(c, cp, p, v2)
        self.assertEqual((r1.regular, r1.current, r1.campaign_price), (1000, 1000, 900))
        self.assertEqual((r2.regular, r2.current, r2.campaign_price), (2000, 1800, 1800))   # 10% of regular 2000

    def test_variants_PER_VARIANT_uses_the_variant_row(self):
        p = make_product(price=0)
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000)
        c = make_campaign()
        cp = add(c, p, DT.PERCENT, 1, variant_mode=VM.PER_VARIANT)    # row-level value must be ignored
        CampaignProductVariant.objects.create(campaign_product=cp, variant=v1, discount_type=DT.PERCENT, discount_value=10)
        CampaignProductVariant.objects.create(campaign_product=cp, variant=v2, discount_type=DT.FIXED, discount_value=500)
        r1, r2 = line(c, cp, p, v1), line(c, cp, p, v2)
        self.assertEqual(r1.campaign_price, 900)
        self.assertEqual(r1.badge_text, "10% OFF")
        self.assertEqual(r2.campaign_price, 1500)
        self.assertEqual(r2.badge_text, "৳500 OFF")                    # unit follows THIS variant's type

    def test_PER_VARIANT_without_row_means_not_discounted_never_dearer_than_normal(self):
        p = make_product(price=0)
        v1 = make_variant(p, price=1000, discount=900, default=True)
        c = make_campaign(discount_base=SRC.REGULAR)
        cp = add(c, p, DT.PERCENT, 10, variant_mode=VM.PER_VARIANT)
        r = line(c, cp, p, v1)
        self.assertEqual(r.campaign_price, 900)      # = current price, NOT 1000
        self.assertIsNone(r.badge_text)
        self.assertIn(WARN_VARIANT_DISCOUNT_MISSING, r.warnings)

    def test_default_variant_is_used_when_no_variant_given(self):
        p = make_product(price=0)
        make_variant(p, price=3000)
        v_default = make_variant(p, price=1000, default=True)
        c = make_campaign()
        cp = add(c, p, DT.PERCENT, 10)
        self.assertEqual(line(c, cp, p).variant_id, v_default.id)

    def test_out_of_stock_default_is_skipped_like_the_product_cards_do(self):
        p = make_product(price=0)
        make_variant(p, price=1000, default=True, qty=0)
        v_in_stock = make_variant(p, price=2000, qty=5)
        c = make_campaign()
        cp = add(c, p, DT.PERCENT, 10)
        self.assertEqual(line(c, cp, p).variant_id, fresh(p).display_variant.id)
        self.assertEqual(line(c, cp, p).variant_id, v_in_stock.id)

    def test_product_with_variants_ignores_product_level_discount_price(self):
        # AddToCart charges variant.discount_price or variant.price - product.discount_price is never used.
        p = make_product(price=500, discount=100)
        v = make_variant(p, price=1000, default=True)
        c = make_campaign()
        r = line(c, add(c, p, DT.PERCENT, 10), p, v)
        self.assertEqual((r.regular, r.current, r.campaign_price), (1000, 1000, 900))

    def test_product_prices_are_never_modified(self):
        p = make_product(price=1000, discount=800)
        c = make_campaign()
        cp = add(c, p, DT.PERCENT, 50)
        line(c, cp, p)
        build_campaign_pricing(c, CampaignProduct.objects.get(pk=cp.pk), fresh(p))
        p.refresh_from_db()
        self.assertEqual((p.price, p.discount_price), (1000, 800))


# ==========================================================================
# GIFTS / OFFERS SWITCHES (SPEC 12)
# ==========================================================================
class EffectiveSwitchTests(TestCase):
    def test_every_inherit_include_exclude_combination(self):
        p = make_product()
        # (campaign switch, product mode) -> effective
        table = [
            (False, SW.INHERIT, False), (True, SW.INHERIT, True),
            (False, SW.INCLUDE, True), (True, SW.INCLUDE, True),
            (False, SW.EXCLUDE, False), (True, SW.EXCLUDE, False),
        ]
        for camp_on, mode, expected in table:
            with self.subTest(campaign_switch=camp_on, mode=mode):
                Campaign.objects.all().delete()
                c = make_campaign(include_product_gifts=camp_on, include_offers=camp_on)
                cp = add(c, p, gift_mode=mode, offer_mode=mode)
                sw = effective_switches(c, cp)
                self.assertEqual(sw.gifts_included, expected)
                self.assertEqual(sw.offers_included, expected)

    def test_gift_and_offer_modes_are_independent(self):
        p = make_product()
        c = make_campaign(include_product_gifts=True, include_offers=False)
        cp = add(c, p, gift_mode=SW.EXCLUDE, offer_mode=SW.INCLUDE)
        self.assertEqual(tuple(effective_switches(c, cp)), (False, True))

    def test_default_is_off(self):
        p = make_product()
        c = make_campaign()
        self.assertEqual(tuple(effective_switches(c, add(c, p))), (False, False))


# ==========================================================================
# STOCK (SPEC 6) - Task 2 fills the data, the structure must already work
# ==========================================================================
class StockLeftTests(TestCase):
    def test_no_limit_means_null(self):
        p = make_product()
        c = make_campaign()
        cp = add(c, p)
        self.assertIsNone(stock_left_for(cp))
        self.assertIsNone(build_campaign_pricing(c, CampaignProduct.objects.get(pk=cp.pk), fresh(p))["stock_limit"])

    def test_stock_left_equals_limit_until_orders_are_tracked(self):
        p = make_product()
        c = make_campaign()
        cp = add(c, p, stock_limit=25)
        self.assertEqual(get_sold_units_map([cp]), {cp.id: 0})
        self.assertEqual(stock_left_for(cp), 25)
        pricing = build_campaign_pricing(c, CampaignProduct.objects.get(pk=cp.pk), fresh(p))
        self.assertEqual((pricing["stock_limit"], pricing["stock_left"]), (25, 25))

    def test_precomputed_sold_units_are_used_and_never_go_negative(self):
        p = make_product()
        c = make_campaign()
        cp = add(c, p, stock_limit=10)
        self.assertEqual(stock_left_for(cp, sold_units=4), 6)
        self.assertEqual(stock_left_for(cp, sold_units=99), 0)

    def test_zero_limit_is_sold_out_not_unlimited(self):
        p = make_product()
        c = make_campaign()
        cp = add(c, p, stock_limit=0)
        self.assertEqual(stock_left_for(cp), 0)


# ==========================================================================
# PUBLIC APIs (SPEC 10)
# ==========================================================================
def make_gift_for(product):
    gift = make_product(price=100, name=f"Gift {next(_counter)}", is_gift_only=True)
    ProductGifting.objects.create(product=product, gift_product=gift, gift_type=PRODUCT_GIFT_TYPE.FREE, value=1)
    return gift


def make_offer_for_all(name="Buy 2 Get 1"):
    offer = Offer.objects.create(name=name, apply_to_all=True)
    OfferTier.objects.create(offer=offer, buy_qty=2, free_qty=1)
    return offer


class CampaignListAPITests(TestCase):
    def get(self, query=""):
        return self.client.get(f"/api/ecom/campaigns/{query}")

    def test_live_first_ending_soonest_then_upcoming_and_hides_draft_and_ended(self):
        now = timezone.now()
        live_late = make_campaign(title="Live Late", end=now + timedelta(days=5))
        live_soon = make_campaign(title="Live Soon", end=now + timedelta(days=1))
        up_later = make_campaign(title="Up Later", start=now + timedelta(days=4), end=now + timedelta(days=6))
        up_soon = make_campaign(title="Up Soon", start=now + timedelta(days=2), end=now + timedelta(days=6))
        make_campaign(title="Draft", is_active=False)
        make_campaign(title="Ended", start=now - timedelta(days=3), end=now - timedelta(days=1))

        res = self.get()
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual([c["title"] for c in data], ["Live Soon", "Live Late", "Up Soon", "Up Later"])
        self.assertEqual([c["status"] for c in data], ["live", "live", "upcoming", "upcoming"])

    def test_item_shape_and_server_now(self):
        make_campaign(title="Black Friday", short_description="Big sale")
        res = self.get()
        item = res.json()["data"][0]
        self.assertEqual(
            set(item),
            {"id", "slug", "title", "short_description", "thumbnail", "banner_desktop", "banner_mobile",
             "status", "start_at", "end_at", "server_now",
             "hero_title", "hero_button_text", "show_in_slider"},
        )
        self.assertEqual(item["slug"], "black-friday")
        self.assertIsNone(item["thumbnail"])
        self.assertTrue(item["server_now"])

    def test_list_never_contains_product_data(self):
        c = make_campaign()
        add(c, make_product())
        self.assertNotIn("products", self.get().json()["data"][0])

    def test_home_filter(self):
        make_campaign(title="On Home", show_on_home=True)
        make_campaign(title="Not On Home", show_on_home=False)
        self.assertEqual([c["title"] for c in self.get("?home=1").json()["data"]], ["On Home"])
        self.assertEqual(len(self.get().json()["data"]), 2)


class CampaignDetailAPITests(TestCase):
    def get(self, slug):
        return self.client.get(f"/api/ecom/campaigns/{slug}/")

    def test_live_returns_cards_with_campaign_pricing(self):
        c = make_campaign(title="Black Friday")
        p = make_product(price=1000, name="Cradle")
        add(c, p, DT.PERCENT, 20)
        res = self.get("black-friday")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["campaign"]["status"], "live")
        self.assertIn("server_now", data["campaign"])
        self.assertEqual({"hero_title", "hero_subtitle", "hero_button_text"} <= set(data["campaign"]), True)
        card = data["products"][0]
        for key in ("id", "slug", "name", "price", "discount_price", "image", "has_variants", "category", "last_update_at"):
            self.assertIn(key, card)
        cp = card["campaign_pricing"]
        self.assertEqual(cp["campaign_slug"], "black-friday")
        self.assertEqual((cp["regular_price"], cp["current_price"], cp["campaign_price"]), (1000, 1000, 800))
        self.assertEqual((cp["strike_price"], cp["savings_amount"], cp["savings_percent"]), (1000, 200, 20))
        self.assertEqual(cp["badge_text"], "20% OFF")
        self.assertEqual(
            set(cp),
            {"campaign_slug", "regular_price", "current_price", "campaign_price", "strike_price", "savings_amount",
             "savings_percent", "badge_text", "stock_limit", "stock_left", "gifts_included", "offers_included", "variants"},
        )
        # card's normal fields are untouched by the campaign
        self.assertEqual(Decimal(str(card["price"])), Decimal("1000"))

    def test_variant_product_card_uses_display_variant_and_lists_all_variants(self):
        c = make_campaign(title="Variants Sale")
        p = make_product(price=0, name="Frame")
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000)
        add(c, p, DT.PERCENT, 10)
        card = self.get("variants-sale").json()["data"]["products"][0]
        cp = card["campaign_pricing"]
        self.assertEqual(cp["campaign_price"], 900)                      # display (default) variant
        self.assertEqual(Decimal(str(card["price"])), Decimal("1000"))   # same variant as the normal card
        self.assertEqual([v["variant_id"] for v in cp["variants"]], [v1.id, v2.id])
        self.assertEqual([v["campaign_price"] for v in cp["variants"]], [900, 1800])
        self.assertEqual(set(cp["variants"][0]), {"variant_id", "regular_price", "current_price", "campaign_price",
                                                  "strike_price", "savings_amount", "savings_percent", "badge_text"})

    def test_card_image_matches_the_normal_product_image(self):
        c = make_campaign(title="Img Sale")
        p = make_product(price=1000)
        add(c, p)
        card = self.get("img-sale").json()["data"]["products"][0]
        self.assertEqual(card["image"], fresh(p).primary_image)    # both None here: no image uploaded

    def test_upcoming_returns_campaign_but_no_products_at_all(self):
        now = timezone.now()
        c = make_campaign(title="Soon", start=now + timedelta(days=1), end=now + timedelta(days=2))
        add(c, make_product(), DT.PERCENT, 50)
        res = self.get("soon")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["data"]["campaign"]["status"], "upcoming")
        self.assertEqual(body["data"]["products"], [])
        self.assertIn("server_now", body["data"]["campaign"])
        self.assertNotIn("campaign_pricing", res.content.decode())

    def test_ended_is_410_with_friendly_message_and_server_now(self):
        now = timezone.now()
        make_campaign(title="Old", start=now - timedelta(days=3), end=now - timedelta(days=1))
        res = self.get("old")
        self.assertEqual(res.status_code, 410)
        self.assertTrue(res.json()["message"])
        self.assertIn("server_now", res.json())

    def test_draft_and_unknown_are_404(self):
        make_campaign(title="Hidden", is_active=False)
        for slug in ("hidden", "does-not-exist"):
            res = self.get(slug)
            self.assertEqual(res.status_code, 404, slug)
            self.assertIn("server_now", res.json())

    def test_inactive_inactive_and_gift_only_products_are_not_listed(self):
        c = make_campaign(title="Filter Sale")
        visible = make_product(name="Visible")
        add(c, visible)
        add(c, make_product(name="Row Off"), is_active=False)
        add(c, make_product(name="Draft Product", status=CATEGORY_PRODUCT_STATUS.DRAFT))
        gift_only = make_product(name="Gift Only", is_gift_only=True)
        CampaignProduct.objects.create(campaign=c, product=gift_only, discount_type=DT.PERCENT, discount_value=10)
        names = [x["name"] for x in self.get("filter-sale").json()["data"]["products"]]
        self.assertEqual(names, ["Visible"])

    def test_products_follow_sort_order(self):
        c = make_campaign(title="Order Sale")
        add(c, make_product(name="B"), sort_order=2)
        add(c, make_product(name="A"), sort_order=1)
        names = [x["name"] for x in self.get("order-sale").json()["data"]["products"]]
        self.assertEqual(names, ["A", "B"])

    def test_query_count_does_not_grow_with_the_number_of_products(self):
        def build(n, slug_title):
            c = make_campaign(title=slug_title)
            for _ in range(n):
                prod = make_product(price=0)
                make_variant(prod, price=1000, default=True)
                make_variant(prod, price=1500)
                add(c, prod, stock_limit=5)
            return c.slug

        small, large = build(2, "Small Sale"), build(8, "Large Sale")
        with CaptureQueriesContext(connection) as q_small:
            self.assertEqual(self.get(small).status_code, 200)
        with CaptureQueriesContext(connection) as q_large:
            res = self.get(large)
        self.assertEqual(len(res.json()["data"]["products"]), 8)
        self.assertEqual(len(q_small), len(q_large), "N+1 detected on the campaign detail endpoint")


class ProductDetailCampaignContextTests(TestCase):
    def detail(self, product, query=""):
        return self.client.get(f"/api/ecom/products/{product.slug}/{query}")

    def test_response_is_identical_without_the_parameter(self):
        p = make_product(price=1000, discount=900, name="Plain")
        before = self.detail(p).json()
        c = make_campaign(title="Live One")
        add(c, p, DT.PERCENT, 50)
        make_campaign(title="Another Live")
        after = self.detail(p).json()
        self.assertEqual(before, after)
        data = after["data"]
        for key in ("campaign_pricing", "campaign_notice", "server_now", "gift_product", "has_gift"):
            self.assertNotIn(key, data)
        self.assertEqual(Decimal(str(data["price"])), Decimal("1000"))
        self.assertEqual(Decimal(str(data["discount_price"])), Decimal("900"))

    def test_empty_campaign_parameter_is_the_normal_response(self):
        p = make_product()
        self.assertEqual(self.detail(p).json(), self.detail(p, "?campaign=").json())

    def test_valid_campaign_adds_pricing_and_leaves_everything_else_alone(self):
        p = make_product(price=1000, discount=900, name="With Campaign")
        normal = self.detail(p).json()["data"]
        c = make_campaign(title="Black Friday", discount_base=SRC.REGULAR, strike_price_display=SRC.REGULAR)
        add(c, p, DT.PERCENT, 20)
        res = self.detail(p, "?campaign=black-friday")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["campaign_pricing"]["campaign_price"], 800)
        self.assertNotIn("campaign_notice", data)
        self.assertIn("server_now", data)
        added = {"campaign_pricing", "server_now", "gift_product", "has_gift"}
        self.assertEqual({k: v for k, v in data.items() if k not in added}, normal)
        # the product's own prices are untouched
        self.assertEqual(Decimal(str(data["price"])), Decimal("1000"))
        self.assertEqual(Decimal(str(data["discount_price"])), Decimal("900"))

    def test_notice_ended(self):
        p = make_product()
        now = timezone.now()
        c = make_campaign(title="Old Sale", start=now - timedelta(days=3), end=now - timedelta(days=1))
        add(c, p)
        data = self.detail(p, "?campaign=old-sale").json()["data"]
        self.assertEqual(data["campaign_notice"], "ended")
        self.assertNotIn("campaign_pricing", data)

    def test_notice_not_started_and_no_pricing_leak(self):
        p = make_product()
        now = timezone.now()
        c = make_campaign(title="Soon Sale", start=now + timedelta(days=1), end=now + timedelta(days=2))
        add(c, p, DT.PERCENT, 90)
        res = self.detail(p, "?campaign=soon-sale")
        data = res.json()["data"]
        self.assertEqual(data["campaign_notice"], "not_started")
        self.assertNotIn("campaign_pricing", data)
        self.assertNotIn("90", [str(v) for v in data.get("campaign_pricing", {}).values()])

    def test_notice_not_in_campaign_for_unknown_draft_missing_or_switched_off_product(self):
        p = make_product()
        other = make_product()
        live = make_campaign(title="Live Sale")
        add(live, other)                                           # p is not in it
        draft = make_campaign(title="Draft Sale", is_active=False)
        add(draft, p)
        off = make_campaign(title="Off Sale")
        add(off, p, is_active=False)                               # row switched off
        for slug in ("live-sale", "draft-sale", "off-sale", "nope"):
            with self.subTest(slug=slug):
                data = self.detail(p, f"?campaign={slug}").json()["data"]
                self.assertEqual(data["campaign_notice"], "not_in_campaign")
                self.assertNotIn("campaign_pricing", data)

    def test_notice_cases_leave_the_rest_of_the_payload_unchanged(self):
        p = make_product(price=1000, discount=800)
        normal = self.detail(p).json()["data"]
        data = self.detail(p, "?campaign=nope").json()["data"]
        self.assertEqual({k: v for k, v in data.items() if k not in ("campaign_notice", "server_now")}, normal)

    def test_variant_pricing_in_product_detail(self):
        p = make_product(price=0)
        v1 = make_variant(p, price=1000, default=True)
        v2 = make_variant(p, price=2000, discount=1500)
        c = make_campaign(title="Var Sale", discount_base=SRC.CURRENT, strike_price_display=SRC.REGULAR)
        add(c, p, DT.PERCENT, 10)
        cp = self.detail(p, "?campaign=var-sale").json()["data"]["campaign_pricing"]
        by_id = {v["variant_id"]: v for v in cp["variants"]}
        self.assertEqual(by_id[v1.id]["campaign_price"], 900)
        self.assertEqual(by_id[v2.id]["campaign_price"], 1350)       # 10% off the CURRENT 1500
        self.assertEqual(by_id[v2.id]["strike_price"], 2000)

    def test_upcoming_and_ended_never_affect_the_normal_price_fields(self):
        p = make_product(price=1000)
        now = timezone.now()
        c = make_campaign(title="Soon", start=now + timedelta(days=1), end=now + timedelta(days=2))
        add(c, p, DT.PERCENT, 50)
        data = self.detail(p, "?campaign=soon").json()["data"]
        self.assertEqual(Decimal(str(data["price"])), Decimal("1000"))

    # ---------------- SPEC 12: gifts ----------------
    def test_gifts_matrix_in_product_detail(self):
        p = make_product(name="Gift Host")
        make_gift_for(p)
        table = [
            (False, SW.INHERIT, False), (True, SW.INHERIT, True),
            (False, SW.INCLUDE, True), (True, SW.INCLUDE, True),
            (False, SW.EXCLUDE, False), (True, SW.EXCLUDE, False),
        ]
        for camp_on, mode, expected in table:
            with self.subTest(campaign_switch=camp_on, mode=mode):
                Campaign.objects.all().delete()
                c = make_campaign(title="Gift Sale", include_product_gifts=camp_on)
                add(c, p, gift_mode=mode)
                data = self.detail(p, "?campaign=gift-sale").json()["data"]
                self.assertEqual(data["campaign_pricing"]["gifts_included"], expected)
                self.assertEqual(data["has_gift"], expected)
                self.assertEqual(len(data["gift_product"]), 1 if expected else 0)
                if expected:
                    self.assertEqual(data["gift_product"][0]["gift_type"], "FREE")
                    self.assertIn("name", data["gift_product"][0]["gift_product"])

    def test_gift_off_for_product_without_gifts_is_still_an_empty_list(self):
        p = make_product()
        c = make_campaign(title="No Gift Sale", include_product_gifts=True)
        add(c, p)
        data = self.detail(p, "?campaign=no-gift-sale").json()["data"]
        self.assertEqual(data["gift_product"], [])
        self.assertFalse(data["has_gift"])             # switched on, but nothing to show

    def test_gifts_matrix_in_campaign_detail_products(self):
        table = [
            (False, SW.INHERIT, False), (True, SW.INHERIT, True),
            (False, SW.INCLUDE, True), (True, SW.EXCLUDE, False),
        ]
        for camp_on, mode, expected in table:
            with self.subTest(campaign_switch=camp_on, mode=mode):
                Campaign.objects.all().delete()
                p = make_product()
                make_gift_for(p)
                c = make_campaign(title="Gift List", include_product_gifts=camp_on)
                add(c, p, gift_mode=mode)
                card = self.client.get("/api/ecom/campaigns/gift-list/").json()["data"]["products"][0]
                self.assertEqual(card["campaign_pricing"]["gifts_included"], expected)
                self.assertEqual(card["has_gift"], expected)
                self.assertEqual(len(card["gift_product"]), 1 if expected else 0)

    # ---------------- SPEC 12: offers ----------------
    def offers(self, product, query=""):
        return self.client.get(f"/api/offers/product/{product.id}/{query}").json()["data"]

    def test_offers_endpoint_is_unchanged_without_the_parameter(self):
        p = make_product()
        make_offer_for_all()
        c = make_campaign(title="Offer Sale")
        add(c, p, offer_mode=SW.EXCLUDE)
        self.assertEqual(len(self.offers(p)["offers"]), 1)             # normal context: offer visible
        self.assertEqual(len(self.offers(p, "?campaign=")["offers"]), 1)

    def test_offers_matrix_in_campaign_context(self):
        p = make_product(name="Offer Host")
        partner = make_product(name="Combo Partner")
        ProductComboPair.objects.create(product_a=p, product_b=partner)
        make_offer_for_all()
        table = [
            (False, SW.INHERIT, False), (True, SW.INHERIT, True),
            (False, SW.INCLUDE, True), (True, SW.INCLUDE, True),
            (False, SW.EXCLUDE, False), (True, SW.EXCLUDE, False),
        ]
        for camp_on, mode, expected in table:
            with self.subTest(campaign_switch=camp_on, mode=mode):
                Campaign.objects.all().delete()
                c = make_campaign(title="Offer Sale", include_offers=camp_on)
                add(c, p, offer_mode=mode)
                # product detail tells the frontend what is effective ...
                detail = self.client.get(f"/api/ecom/products/{p.slug}/?campaign=offer-sale").json()["data"]
                self.assertEqual(detail["campaign_pricing"]["offers_included"], expected)
                self.assertNotIn("offers", detail)                      # never inline offer data
                # ... and the offers endpoint returns no offer data when they are off
                data = self.offers(p, "?campaign=offer-sale")
                self.assertEqual(len(data["offers"]), 1 if expected else 0)
                # combo suggestions are NOT affected either way
                self.assertEqual([x["product_id"] for x in data["combos"]], [partner.id])

    def test_offers_are_not_suppressed_when_the_campaign_does_not_apply(self):
        p = make_product()
        make_offer_for_all()
        now = timezone.now()
        ended = make_campaign(title="Ended Sale", start=now - timedelta(days=3), end=now - timedelta(days=1))
        add(ended, p, offer_mode=SW.EXCLUDE)
        draft = make_campaign(title="Draft Sale", is_active=False)
        add(draft, p, offer_mode=SW.EXCLUDE)
        other = make_campaign(title="Other Sale")                      # product not in it
        add(other, make_product(), offer_mode=SW.EXCLUDE)
        for slug in ("ended-sale", "draft-sale", "other-sale", "unknown"):
            with self.subTest(slug=slug):
                self.assertEqual(len(self.offers(p, f"?campaign={slug}")["offers"]), 1)

    def test_normal_lines_of_the_same_product_are_not_affected_by_the_exclusion(self):
        p = make_product()
        make_gift_for(p)
        make_offer_for_all()
        c = make_campaign(title="Excl Sale")
        add(c, p, gift_mode=SW.EXCLUDE, offer_mode=SW.EXCLUDE)
        self.assertEqual(len(self.offers(p)["offers"]), 1)             # normal page still has its offer
        self.assertNotIn("has_gift", self.detail(p).json()["data"])    # and the normal payload is untouched
