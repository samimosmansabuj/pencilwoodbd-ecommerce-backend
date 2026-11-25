import hashlib
from django.db import models
from django.contrib.auth.models import AbstractUser
from pencilwoodbd.choices import USER_TYPE, TrackSettingsModeChoices,TrackSettingsScopeChoices, BlockedIdentityReasonChoices, BlockedOrderModeChoices, DEFAULT_BLOCKED_MESSAGE, CourierCheckProviderChoices, CourierLowRatioActionChoices, CourierRetentionUnitChoices, CourierNoticeClearModeChoices, DEFAULT_COURIER_HARD_BLOCK_MESSAGE, DEFAULT_COURIER_OTP_MESSAGE, DEFAULT_COURIER_WHATSAPP_MESSAGE, DEFAULT_COURIER_WHATSAPP_PREFILL

from django.utils import timezone
from django.db.models import Q
class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    google_id = models.CharField(max_length=64, unique=True, blank=True, null=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPE.choices, default=USER_TYPE.CUSTOMER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        if self.phone:
            from .utils import normalize_bd_phone
            normalized = normalize_bd_phone(self.phone)
            if normalized:
                self.phone = normalized
        if self.email == "":
            self.email = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email or self.phone or self.username


class GoogleIdentity(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="google_identities")
    google_id = models.CharField(max_length=64, unique=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email or self.google_id} -> {self.user_id}"


class Customer(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='customer_profile')
    company = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True, null=True)
    second_phone = models.CharField(max_length=20, blank=True, null=True)
    whatsapp = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=200, blank=True, null=True)
    source = models.CharField(max_length=100, blank=True, null=True, default='Others')
    has_password = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.phone:
            from .utils import normalize_bd_phone
            normalized = normalize_bd_phone(self.phone)
            if normalized:
                self.phone = normalized
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=255, unique=True)
    can_read = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)


# ============ IP / DEVICE ORDER TRACKING & BLOCKING ============
def make_device_hash(ip, user_agent):
    raw = f"{ip}|{user_agent or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TrackSettings(models.Model):
    ModeChoices = TrackSettingsModeChoices  
    ScopeChoices = TrackSettingsScopeChoices  

    mode = models.CharField(max_length=20, choices=TrackSettingsModeChoices.choices, default=TrackSettingsModeChoices.LIFETIME, help_text="Default: Lifetime. 'Consecutive' hole kono order delivered hole counter reset hobe.")
    scope = models.CharField(max_length=20, choices=TrackSettingsScopeChoices.choices, default=TrackSettingsScopeChoices.ORDER, help_text="Default: Order-wise. Order-wise hole ekta order e jotogula product e cancel thakuk na keno, seta 1 cancel hisebe count hobe. Product-wise hole prottek product er cancel count alada vabe track hobe.")
    cancel_threshold = models.PositiveIntegerField(default=5, help_text="Koto bar cancel hole auto-block hobe. Default: 5")
    is_auto_block_enabled = models.BooleanField(default=True, help_text="Off korle auto-block hobe na, shudhu count track hobe.")
    ecom_blocked_mode = models.CharField(max_length=10, choices=BlockedOrderModeChoices.choices, default=BlockedOrderModeChoices.OTP, help_text="E-commerce checkout: blocked user er jonno OTP on/off. OTP = OTP diye order, Allow = OTP charai order nibe, Deny = order nibe na, message dekhabe.")
    blocked_message = models.TextField(default=DEFAULT_BLOCKED_MESSAGE, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Track Setting"
        verbose_name_plural = "Track Settings"

    def save(self, *args, **kwargs):
        self.pk = 1  
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Track Settings ({self.mode}, threshold={self.cancel_threshold})"


class OrderTrackRecord(models.Model):
    order = models.ForeignKey(
        "order.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="track_records"
    )
    ip_address = models.GenericIPAddressField(db_index=True)
    device_hash = models.CharField(max_length=64, db_index=True)
    user_agent = models.TextField(blank=True, null=True)

    status_at_capture = models.CharField(max_length=50, blank=True, null=True)
    is_identity_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Order Track Record"
        verbose_name_plural = "Order Track Records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ip_address"]),
            models.Index(fields=["device_hash"]),
        ]

    def __str__(self):
        return f"{self.ip_address} | {self.device_hash[:8]} | Order: {self.order_id}"


class BlockedIdentity(models.Model):
    ReasonChoices = BlockedIdentityReasonChoices  

    ip_address = models.GenericIPAddressField(db_index=True, blank=True, null=True)
    device_hash = models.CharField(max_length=64, db_index=True, blank=True, null=True)
    phone = models.CharField(max_length=20, db_index=True, blank=True, null=True)

    reason = models.CharField(max_length=30, choices=BlockedIdentityReasonChoices.choices, default=BlockedIdentityReasonChoices.AUTO_CANCEL_LIMIT)
    note = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True, db_index=True)

    blocked_at = models.DateTimeField(auto_now_add=True)
    blocked_by = models.ForeignKey(
        "authentication.CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blocks_made", help_text="Null hole system auto-block."
    )

    unblocked_at = models.DateTimeField(null=True, blank=True)
    unblocked_by = models.ForeignKey(
        "authentication.CustomUser", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blocks_removed"
    )

    cancel_count_at_block_time = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Blocked Identity"
        verbose_name_plural = "Blocked Identities"
        ordering = ["-blocked_at"]

    def unblock(self, staff_user=None):
        self.is_active = False
        self.unblocked_at = timezone.now()
        self.unblocked_by = staff_user
        self.save(update_fields=["is_active", "unblocked_at", "unblocked_by"])

        query = Q()
        if self.ip_address:
            query |= Q(ip_address=self.ip_address)
        if self.device_hash:
            query |= Q(device_hash=self.device_hash)
        if query:
            OrderTrackRecord.objects.filter(query).update(is_identity_blocked=False)

    def __str__(self):
        parts = []
        if self.ip_address:
            parts.append(str(self.ip_address))
        if self.device_hash:
            parts.append(self.device_hash[:8])
        if self.phone:
            parts.append(self.phone)
        label = " / ".join(parts) if parts else "Unknown"
        return f"{label} - {'Active' if self.is_active else 'Unblocked'}"


class CourierCheckSettings(models.Model):
    is_enabled = models.BooleanField(default=False)
    provider = models.CharField(max_length=30, choices=CourierCheckProviderChoices.choices, default=CourierCheckProviderChoices.BDCOURIER)
    api_base_url = models.CharField(max_length=255, default="https://api.bdcourier.com")
    api_endpoint = models.CharField(max_length=100, default="/courier-check")
    api_key = models.CharField(max_length=255, blank=True, default="")
    timeout_seconds = models.PositiveSmallIntegerField(default=8)
    api_retries = models.PositiveSmallIntegerField(default=2)
    auto_check_new_numbers = models.BooleanField(default=True)
    auto_check_hourly_limit = models.PositiveIntegerField(default=100)

    min_success_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=70)
    min_parcels_to_evaluate = models.PositiveIntegerField(default=1)
    low_ratio_action = models.CharField(max_length=10, choices=CourierLowRatioActionChoices.choices, default=CourierLowRatioActionChoices.OTP)
    otp_message = models.TextField(blank=True, default=DEFAULT_COURIER_OTP_MESSAGE)
    whatsapp_message = models.TextField(blank=True, default=DEFAULT_COURIER_WHATSAPP_MESSAGE)
    whatsapp_number = models.CharField(max_length=20, blank=True, default="")
    whatsapp_prefill_text = models.CharField(max_length=255, blank=True, default=DEFAULT_COURIER_WHATSAPP_PREFILL)

    show_badges = models.BooleanField(default=True)
    warn_margin = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    apply_on_ecom = models.BooleanField(default=True)
    apply_on_landing = models.BooleanField(default=True)
    fail_open = models.BooleanField(default=True)
    cache_hours = models.PositiveIntegerField(default=6)
    ignored_couriers = models.CharField(max_length=255, blank=True, default="")

    hard_block_enabled = models.BooleanField(default=False)
    hard_block_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    hard_block_message = models.TextField(blank=True, default=DEFAULT_COURIER_HARD_BLOCK_MESSAGE)
    hard_block_contact = models.CharField(max_length=60, blank=True, default="")

    restricted_clear_mode = models.CharField(max_length=10, choices=CourierNoticeClearModeChoices.choices, default=CourierNoticeClearModeChoices.MANUAL)
    restricted_expire_forever = models.BooleanField(default=False)
    restricted_expire_value = models.PositiveIntegerField(default=7)
    restricted_expire_unit = models.CharField(max_length=10, choices=CourierRetentionUnitChoices.choices, default=CourierRetentionUnitChoices.DAY)
    restricted_cleared_at = models.DateTimeField(null=True, blank=True)
    retention_forever = models.BooleanField(default=True)
    retention_value = models.PositiveIntegerField(default=90)
    retention_unit = models.CharField(max_length=10, choices=CourierRetentionUnitChoices.choices, default=CourierRetentionUnitChoices.DAY)
    last_cleanup_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Courier Check Setting"
        verbose_name_plural = "Courier Check Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def ignored_courier_list(self):
        return [s.strip() for s in (self.ignored_couriers or "").split(",") if s.strip()]

    @property
    def masked_api_key(self):
        key = self.api_key or ""
        return f"{key[:4]}{'*' * 8}{key[-4:]}" if len(key) > 10 else ("*" * len(key))

    def __str__(self):
        return f"Courier Check ({'ON' if self.is_enabled else 'OFF'}, min {self.min_success_ratio}%)"


class CourierCheckLog(models.Model):
    phone = models.CharField(max_length=20, db_index=True)
    provider = models.CharField(max_length=30, default="bdcourier")
    source = models.CharField(max_length=20, blank=True, default="")
    is_error = models.BooleanField(default=False)
    error_message = models.CharField(max_length=500, blank=True, default="")
    total_parcels = models.PositiveIntegerField(default=0)
    success_parcels = models.PositiveIntegerField(default=0)
    cancelled_parcels = models.PositiveIntegerField(default=0)
    rate_only_parcels = models.PositiveIntegerField(default=0)
    success_ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    courier_breakdown = models.JSONField(default=list, blank=True)
    reports = models.JSONField(default=list, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Courier Check Log"
        verbose_name_plural = "Courier Check Logs"

    def __str__(self):
        return f"{self.phone} | {self.success_ratio}% | {self.created_at:%Y-%m-%d %H:%M}"


class CourierNumberRetention(models.Model):
    phone = models.CharField(max_length=20, unique=True)
    keep_forever = models.BooleanField(default=False)
    value = models.PositiveIntegerField(default=30)
    unit = models.CharField(max_length=10, choices=CourierRetentionUnitChoices.choices, default=CourierRetentionUnitChoices.DAY)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Courier Number Retention"
        verbose_name_plural = "Courier Number Retentions"

    def __str__(self):
        return f"{self.phone} | {'forever' if self.keep_forever else f'{self.value} {self.unit}'}"


class CourierRestrictedAttempt(models.Model):
    attempt = models.OneToOneField("order.OrderAttempt", on_delete=models.CASCADE, related_name="courier_restriction")
    phone = models.CharField(max_length=20, db_index=True)
    ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    limit = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=20, blank=True, default="")
    times = models.PositiveIntegerField(default=1)
    first_at = models.DateTimeField(default=timezone.now)
    last_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-last_at"]
        verbose_name = "Courier Restricted Attempt"
        verbose_name_plural = "Courier Restricted Attempts"

    def __str__(self):
        return f"{self.phone} | {self.ratio}% < {self.limit}% | x{self.times}"
