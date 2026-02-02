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
    Pending = "Pending"
    Confirm = "Confirm"
    Shipped = "Shipped"
    Ready_to_Ship = "Ready to Ship"
    Out_for_Delivery = "Out for Delivery"
    Processing = "Processing"
    Delivered = "Delivered"
    Cancel = "Cancel"
    Return = "Return"

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

# ==============================================================


# ----- PRODUCT SECTION CHOICES OPTION -----
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

