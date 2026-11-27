from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from pencilwoodbd.choices import (
    CAMPAIGN_BADGE_MODE,
    CAMPAIGN_DELIVERY_AMOUNT_SOURCE,
    CAMPAIGN_DELIVERY_BASIS,
    CAMPAIGN_DELIVERY_MODE,
    CAMPAIGN_DISCOUNT_TYPE,
    CAMPAIGN_MIXED_CART_DELIVERY,
    CAMPAIGN_PRICE_SOURCE,
    CAMPAIGN_SURFACE,
    CAMPAIGN_SWITCH_MODE,
    CAMPAIGN_VARIANT_MODE,
)
from product.models import Product, ProductVariant
from .pricing import get_campaign_status
from .pricing import find_overlap_conflicts

BADGE_LABEL_MAX_LENGTH = 20


def default_price_surfaces():
    return list(CAMPAIGN_SURFACE.values)


def normalize_surface(value):
    return str(value or "").strip().upper().replace("-", "_")


def validate_delivery_config(value):
    if value in (None, ""):
        return
    if not isinstance(value, dict):
        raise ValidationError('Delivery config must be a JSON object like {"all": 80}.')
    for key, amount in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValidationError("Delivery config keys must be district names or 'all'.")
        if isinstance(amount, bool) or amount in (None, ""):
            raise ValidationError(f"Delivery charge for '{key}' must be a number.")
        try:
            number = Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(f"Delivery charge for '{key}' must be a number.")
        if not number.is_finite() or number < 0:
            raise ValidationError(f"Delivery charge for '{key}' cannot be negative.")


def validate_discount(discount_type, discount_value, field_name="discount_value"):
    if discount_value is None:
        raise ValidationError({field_name: "Discount value is required."})
    value = Decimal(str(discount_value))
    if discount_type == CAMPAIGN_DISCOUNT_TYPE.PERCENT:
        if not (Decimal("0") < value < Decimal("100")):
            raise ValidationError({field_name: "Percent discount must be greater than 0 and less than 100."})
    elif discount_type == CAMPAIGN_DISCOUNT_TYPE.FIXED:
        if value <= 0:
            raise ValidationError({field_name: "Fixed discount must be greater than 0."})
    else:
        raise ValidationError({"discount_type": "Unknown discount type."})


def _unique_campaign_slug(title, exclude_pk=None):
    base = slugify(title or "")[:200] or "campaign"
    slug, n = base, 1
    qs = Campaign.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Campaign(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    short_description = models.CharField(max_length=500, blank=True, default="")
    thumbnail = models.ImageField(upload_to="campaign/thumbnail/", blank=True, null=True)
    banner_desktop = models.ImageField(upload_to="campaign/banner/desktop/", blank=True, null=True)
    banner_mobile = models.ImageField(upload_to="campaign/banner/mobile/", blank=True, null=True)
    hero_title = models.CharField(max_length=255, blank=True, default="")
    hero_subtitle = models.CharField(max_length=500, blank=True, default="")
    hero_button_text = models.CharField(max_length=100, blank=True, default="")
    sort_order = models.IntegerField(default=0)
    show_on_home = models.BooleanField(default=False)
    show_in_slider = models.BooleanField(default=False, help_text="Show this campaign (with a countdown) in the home page slider.")

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_active = models.BooleanField(default=False, help_text="Manual master switch. Off = draft.")

    discount_base = models.CharField(
        max_length=10, choices=CAMPAIGN_PRICE_SOURCE.choices, default=CAMPAIGN_PRICE_SOURCE.CURRENT,
        help_text="Which price the discount is calculated from.")
    strike_price_display = models.CharField(
        max_length=10, choices=CAMPAIGN_PRICE_SOURCE.choices, default=CAMPAIGN_PRICE_SOURCE.CURRENT,
        help_text="Which price is shown struck-through.")
    badge_mode = models.CharField(
        max_length=20, choices=CAMPAIGN_BADGE_MODE.choices, default=CAMPAIGN_BADGE_MODE.DISCOUNT_ONLY)
    badge_label = models.CharField(
        max_length=BADGE_LABEL_MAX_LENGTH, blank=True, default="",
        help_text="Defaults to the campaign title (first 20 characters).")

    price_surfaces = models.JSONField(default=default_price_surfaces, blank=True)

    allow_overlap = models.BooleanField(default=False)
    allow_coupon = models.BooleanField(default=False)
    include_product_gifts = models.BooleanField(default=False, help_text="Apply product free gifts on campaign items.")
    include_offers = models.BooleanField(default=False, help_text="Apply buy-X-get-Y offers on campaign items.")

    delivery_mode = models.CharField(
        max_length=10, choices=CAMPAIGN_DELIVERY_MODE.choices, default=CAMPAIGN_DELIVERY_MODE.NORMAL)
    delivery_amount_source = models.CharField(
        max_length=15, choices=CAMPAIGN_DELIVERY_AMOUNT_SOURCE.choices,
        default=CAMPAIGN_DELIVERY_AMOUNT_SOURCE.SAME_FOR_ALL)
    delivery_config = models.JSONField(
        default=dict, blank=True, validators=[validate_delivery_config],
        help_text='Same format as the site-wide delivery config, e.g. {"all": 80} or {"Dhaka": 60, "all": 100}')
    delivery_basis = models.CharField(
        max_length=12, choices=CAMPAIGN_DELIVERY_BASIS.choices, default=CAMPAIGN_DELIVERY_BASIS.PER_ORDER)
    mixed_cart_delivery = models.CharField(
        max_length=10, choices=CAMPAIGN_MIXED_CART_DELIVERY.choices, default=CAMPAIGN_MIXED_CART_DELIVERY.COMBINED)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="campaigns_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-start_at", "-id"]
        indexes = [models.Index(fields=["is_active", "start_at", "end_at"], name="campaign_window_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=models.F("start_at")), name="campaign_end_after_start"),
        ]

    def __str__(self):
        return self.title

    @property
    def status(self):
        return get_campaign_status(self)

    def allows_surface(self, surface):
        if not surface:
            return True
        return normalize_surface(surface) in (self.price_surfaces or [])

    def clean(self):
        errors = {}
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            errors["end_at"] = "End time must be after the start time."
        try:
            validate_delivery_config(self.delivery_config)
        except ValidationError as exc:
            errors["delivery_config"] = exc.messages
        if (self.delivery_mode == CAMPAIGN_DELIVERY_MODE.CUSTOM
                and self.delivery_amount_source == CAMPAIGN_DELIVERY_AMOUNT_SOURCE.SAME_FOR_ALL
                and not self.delivery_config):
            errors.setdefault("delivery_config", "Custom delivery with the same charge for all products needs a delivery config.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_campaign_slug(self.title, exclude_pk=self.pk)
        if not (self.badge_label or "").strip():
            self.badge_label = (self.title or "")[:BADGE_LABEL_MAX_LENGTH]
        super().save(*args, **kwargs)


class CampaignProduct(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="campaign_products")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="campaign_products")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    discount_type = models.CharField(
        max_length=10, choices=CAMPAIGN_DISCOUNT_TYPE.choices, default=CAMPAIGN_DISCOUNT_TYPE.PERCENT)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    variant_mode = models.CharField(
        max_length=12, choices=CAMPAIGN_VARIANT_MODE.choices, default=CAMPAIGN_VARIANT_MODE.ALL_SAME)

    stock_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Max units sellable at the campaign price (all variants together). Empty = no limit.")

    gift_mode = models.CharField(
        max_length=10, choices=CAMPAIGN_SWITCH_MODE.choices, default=CAMPAIGN_SWITCH_MODE.INHERIT)
    offer_mode = models.CharField(
        max_length=10, choices=CAMPAIGN_SWITCH_MODE.choices, default=CAMPAIGN_SWITCH_MODE.INHERIT)

    discount_base_override = models.CharField(
        max_length=10, choices=CAMPAIGN_PRICE_SOURCE.choices, blank=True, default="")
    strike_price_override = models.CharField(
        max_length=10, choices=CAMPAIGN_PRICE_SOURCE.choices, blank=True, default="")

    delivery_config = models.JSONField(null=True, blank=True, validators=[validate_delivery_config])

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "product"], name="campaign_product_unique"),
        ]

    def __str__(self):
        return f"{self.campaign_id}: {self.product_id}"

    def clean(self):
        if self.variant_mode == CAMPAIGN_VARIANT_MODE.ALL_SAME:
            validate_discount(self.discount_type, self.discount_value)

        try:
            validate_delivery_config(self.delivery_config)
        except ValidationError as exc:
            raise ValidationError({"delivery_config": exc.messages})

        if self.product_id and self.product.is_gift_only:
            raise ValidationError({"product": "A gift-only product cannot be sold in a campaign."})

        if self.campaign_id and self.product_id and self.is_active:
            conflicts = find_overlap_conflicts(self.campaign, [self.product_id])
            if conflicts:
                c = conflicts[0]
                raise ValidationError({
                    "product": f"'{c['product_name']}' is already in the overlapping campaign "
                               f"'{c['campaign_title']}'. Enable 'allow overlap' on both campaigns or change the dates."
                })


class CampaignProductVariant(models.Model):
    campaign_product = models.ForeignKey(CampaignProduct, on_delete=models.CASCADE, related_name="variant_discounts")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="campaign_discounts")
    discount_type = models.CharField(
        max_length=10, choices=CAMPAIGN_DISCOUNT_TYPE.choices, default=CAMPAIGN_DISCOUNT_TYPE.PERCENT)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["campaign_product", "variant"], name="campaign_product_variant_unique"),
            models.CheckConstraint(
                condition=(
                    Q(discount_type=CAMPAIGN_DISCOUNT_TYPE.PERCENT, discount_value__gt=0, discount_value__lt=100)
                    | Q(discount_type=CAMPAIGN_DISCOUNT_TYPE.FIXED, discount_value__gt=0)
                ),
                name="campaign_variant_discount_valid",
            ),
        ]

    def __str__(self):
        return f"{self.campaign_product_id}: variant {self.variant_id}"

    def clean(self):
        validate_discount(self.discount_type, self.discount_value)
        if self.campaign_product_id and self.variant_id:
            if self.variant.product_id != self.campaign_product.product_id:
                raise ValidationError({"variant": "This variant belongs to a different product."})
