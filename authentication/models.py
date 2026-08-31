import hashlib
from django.db import models
from django.contrib.auth.models import AbstractUser
from pencilwoodbd.choices import USER_TYPE, TrackSettingsModeChoices,TrackSettingsScopeChoices, BlockedIdentityReasonChoices
from django.utils import timezone
from django.db.models import Q
class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
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