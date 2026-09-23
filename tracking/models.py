import uuid
from django.db import models


class EVENT_TYPE(models.TextChoices):
    PAGE_VIEW = "page_view", "Page View"
    PRODUCT_VIEW = "product_view", "Product View"
    CATEGORY_VIEW = "category_view", "Category View"
    SEARCH = "search", "Search"
    ADD_TO_CART = "add_to_cart", "Add To Cart"
    REMOVE_FROM_CART = "remove_from_cart", "Remove From Cart"
    WISHLIST_ADD = "wishlist_add", "Wishlist Add"
    WISHLIST_REMOVE = "wishlist_remove", "Wishlist Remove"
    CHECKOUT_START = "checkout_start", "Checkout Start"
    ORDER_PLACED = "order_placed", "Order Placed"
    LOGIN = "login", "Login"
    SIGNUP = "signup", "Signup"
    CUSTOM = "custom", "Custom"


class VisitorProfile(models.Model):
    
    visitor_id = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        "authentication.Customer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="visitor_profiles"
    )

    first_ip = models.GenericIPAddressField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    utm_source = models.CharField(max_length=100, null=True, blank=True)
    utm_medium = models.CharField(max_length=100, null=True, blank=True)
    utm_campaign = models.CharField(max_length=100, null=True, blank=True)
    landing_url = models.CharField(max_length=500, null=True, blank=True)
    referrer = models.CharField(max_length=500, null=True, blank=True)

    total_page_views = models.PositiveIntegerField(default=0)
    total_visits = models.PositiveIntegerField(default=0)

    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["customer", "-last_seen"]),
        ]
        verbose_name = "Visitor Profile"
        verbose_name_plural = "Visitor Profiles"

    def __str__(self):
        return f"{self.customer or 'Guest'} | {str(self.visitor_id)[:8]}"


class ActivityEvent(models.Model):
    visitor = models.ForeignKey(VisitorProfile, on_delete=models.CASCADE, related_name="events")
    customer = models.ForeignKey(
        "authentication.Customer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="activity_events"
    )

    event_type = models.CharField(
        max_length=30, choices=EVENT_TYPE.choices, default=EVENT_TYPE.PAGE_VIEW, db_index=True
    )

    page_url = models.CharField(max_length=500, blank=True, null=True)
    page_title = models.CharField(max_length=255, blank=True, null=True)
    referrer = models.CharField(max_length=500, blank=True, null=True)

    product = models.ForeignKey(
        "product.Product", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="activity_events"
    )

    meta = models.JSONField(blank=True, null=True, default=dict)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["visitor", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]
        verbose_name = "Activity Event"
        verbose_name_plural = "Activity Events"

    def __str__(self):
        return f"{self.event_type} | visitor#{self.visitor_id} | {self.created_at:%Y-%m-%d %H:%M}"
