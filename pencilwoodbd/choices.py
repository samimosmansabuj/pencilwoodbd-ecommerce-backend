from django.db import models


# ----- ACCOUNT SECTION CHOICES OPTION -----
class USER_TYPE(models.TextChoices):
    CUSTOMER = "customer"
    STAFF = "staff"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# ----- ORDER SECTION CHOICES OPTION -----
class PAYMENT_TYPE(models.TextChoices):
    COD = "COD"
    Online = "Online"
    Partial = "Partial"

class PAYMENT_STATUS(models.TextChoices):
    Paid = "Paid"
    Unpaid = "Unpaid"
    Partial = "Partial"


class STATUS(models.TextChoices):
# class ORDER_STATUS(models.TextChoices):
    NEW = "new"
    FOLLOW_UP = "follow_up"
    CONFIRMED = "confirmed"
    TOKEN_PRINT = "token_print"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"

class ORDER_REQUEST_STATUS(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    CANCELLED = "cancelled", "Cancelled"
    CONVERTED = "converted", "Converted"

class REVIEW_STATUS(models.TextChoices):
    PENDING = "Pending"
    APPROVED = "Approved"
    DELETE = "Delete"

class DELIVERY_TYPE(models.TextChoices):
    HOME_DELIVERY = "Home Delivery"
    PICKUP = "Pickup"
# ==============================================================


# ----- MARKETING SECTION CHOICES OPTION -----
class MarketingIntegrationProviderChoices(models.TextChoices):
    facebook_pixel = "facebook_pixel"
    facebook_capi = "facebook_capi"
    gtm = "gtm"
    ga4 = "ga4"

class MarketingIntegrationStatusChoices(models.TextChoices):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class EmailConfigMailType(models.TextChoices):
    INFO  = "info"
    NO_REPLY  = "no_reply"
    CONTACT  = "contact"
    CAREER  = "career"

class EmailConfigServerType(models.TextChoices):
    SMTP = "smtp"
    API = "api"

# ----- COUPON SECTION CHOICES -----

class CouponCustomerConditionChoices(models.TextChoices):
    ANY = "ANY", "Any Customer"
    FIRST_ORDER = "FIRST_ORDER", "First Order Only"
    EXISTING = "EXISTING", "Existing Customer (has 1+ previous order)"
    MIN_ORDERS = "MIN_ORDERS", "At Least N Previous Orders"


class CouponOrderHistoryScopeChoices(models.TextChoices):
    ALL_ORDERS = "ALL_ORDERS", "Count orders across the whole store"
    SAME_SCOPE = "SAME_SCOPE", "Count only orders within this coupon's Landing Page/Product"
    
    
# ==============================================================


# ----- PRODUCT SECTION CHOICES OPTION -----
class ATTRIBUTE_TYPE(models.TextChoices):
    TEXT = "text"
    NUMBER = "number"
    DROPDOWN = "dropdown"
    COLOR = "color"
    SWATCH = "swatch"

class CATEGORY_PRODUCT_STATUS(models.TextChoices):
    ACTIVE = "Active"
    DEACTIVE = "Deactive"
    DELETE = "Trash"
    DRAFT = "Draft"

class PRODUCT_TYPE(models.TextChoices):
    SIMPLE = "simple"
    VARIABLE = "variable"
    DIGITAL = "digital"
    SERVICE = "service"

class PRODUCT_MEDIA_TYPE(models.TextChoices):
    IMAGE = "image"
    VIDEO = "video"

class PRODUCT_MEDIA_ROLE(models.TextChoices):
    PRIMARY = "primary"
    GALLERY = "gallery"
    ATTRIBUTE = "attribute"
    HERO = "hero"

class PRODUCT_GIFT_TYPE(models.TextChoices):
    DISCOUNT = "DISCOUNT"
    FLAT = "FLAT"
    FREE = "FREE"

# ==============================================================

class ORDER_REQUEST_WORK_STATUS(models.TextChoices):
    NONE = "none", "None"
    DESIGN = "design", "Design"
    CORRECTION = "correction", "Correction"
    CALL = "call", "Call"
    KNOCK = "knock", "Knock"
    OTHER = "other", "Other"
    DONE = "done", "Done"
    HOLD = "hold", "Hold"
    CANCEL = "cancel", "Cancel"

class INVENTORY_TYPE(models.TextChoices):
    IN_STOCK = "in_stock", "In Stock"
    OUT_OF_STOCK = "out_of_stock", "Out of Stock"
    UNLIMITED = "unlimited", "Unlimited"

class ORDER_SOURCE(models.TextChoices):
    WEBSITE = "Website", "Website"
    LANDING_PAGE = "Landing Page", "Landing Page"
    FACEBOOK = "Facebook", "Facebook"
    INSTAGRAM = "Instagram", "Instagram"
    WHATSAPP = "WhatsApp", "WhatsApp"
    REFERRAL = "Referral", "Referral"
    OTHERS = "Others", "Others"

# ----- IP / DEVICE TRACKING & BLOCKING SECTION -----
class TrackSettingsModeChoices(models.TextChoices):
    LIFETIME = "lifetime", "Lifetime (all-time cancel count)"
    CONSECUTIVE = "consecutive", "Consecutive (back-to-back cancels, resets on delivery)"

class TrackSettingsScopeChoices(models.TextChoices):
    ORDER = "order", "Order-wise (count cancelled per orders) [Default]"
    PRODUCT = "product", "Product-wise (count cancels per individual product)"

class BlockedIdentityReasonChoices(models.TextChoices):
    AUTO_CANCEL_LIMIT = "auto_cancel_limit", "Auto: Cancel limit exceeded"
    MANUAL = "manual", "Manually blocked by admin"

class ManualBlockScopeChoices(models.TextChoices):
    ALL = "all", "IP + Device + Phone"
    PHONE_ONLY = "phone_only", "Phone Only"
    IP_DEVICE_ONLY = "ip_device_only", "IP + Device Only"