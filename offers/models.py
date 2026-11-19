from django.db import models
from django.utils import timezone

from pencilwoodbd.choices import OFFER_GIFT_MODE, OFFER_COUNT_MODE
from product.models import Product, ProductVariant, Category


class Offer(models.Model):
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    priority = models.IntegerField(default=0, help_text="Higher runs first. A cart item is used by only one offer.")

    count_mode = models.CharField(
        max_length=10, choices=OFFER_COUNT_MODE.choices, default=OFFER_COUNT_MODE.ALL)
    gift_mode = models.CharField(max_length=10, choices=OFFER_GIFT_MODE.choices, default=OFFER_GIFT_MODE.CHOOSE)
    require_selection = models.BooleanField(
        default=True, help_text="CHOOSE mode: customer must pick all free items before placing the order")
    repeat = models.BooleanField(
        default=False, help_text="Repeat the matched tier for every full set (buy 4 on a 'buy 2 get 1' tier -> 2 free)")
    max_free_per_order = models.PositiveIntegerField(null=True, blank=True)

    apply_to_all = models.BooleanField(default=False, help_text="Every (non-gift) product counts toward this offer")
    trigger_products = models.ManyToManyField(Product, blank=True, related_name="triggered_offers")
    trigger_categories = models.ManyToManyField(Category, blank=True, related_name="triggered_offers")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "-id"]

    def __str__(self):
        return self.name

    def is_running(self, now=None):
        now = now or timezone.now()
        if not self.is_active:
            return False
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True


class OfferTier(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="tiers")
    buy_qty = models.PositiveIntegerField()
    free_qty = models.PositiveIntegerField(default=1, help_text="Used in CHOOSE mode (how many free picks)")

    class Meta:
        ordering = ["buy_qty"]
        unique_together = [("offer", "buy_qty")]

    def __str__(self):
        return f"{self.offer_id}: buy {self.buy_qty} -> {self.free_qty} free"


class OfferGift(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="gifts")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="offer_gifts")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    tier = models.ForeignKey(OfferTier, null=True, blank=True, on_delete=models.CASCADE, related_name="gifts")
    quantity = models.PositiveIntegerField(default=1)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.variant_id and self.product_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "This variant belongs to a different product."})

    def __str__(self):
        return f"{self.offer_id} gift {self.product_id} x{self.quantity}"


class ProductComboPair(models.Model):
    product_a = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="combo_pairs_a")
    product_b = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="combo_pairs_b")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("product_a", "product_b")]

    def __str__(self):
        return f"{self.product_a_id} + {self.product_b_id}"