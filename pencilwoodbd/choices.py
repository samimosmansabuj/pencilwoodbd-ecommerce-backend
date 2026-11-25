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
    HOLD = "hold"
    TOKEN_PRINT = "token_print"
    READY_TO_SHIP = "ready_to_ship"
    PARCEL_REQUESTED = "parcel_requested"
    PARCEL_CREATED = "parcel_created"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_PROCESSING = "return_processing"
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

class BlockedOrderModeChoices(models.TextChoices):
    OTP = "otp", "OTP ON - Blocked user must verify OTP to order"
    ALLOW = "allow", "OTP OFF - Allow order directly (no OTP)"
    DENY = "deny", "OTP OFF - Do not take order, show blocked message"

DEFAULT_BLOCKED_MESSAGE = "আপনার অ্যাকাউন্ট ব্লক করা হয়েছে। অনুগ্রহ করে আমাদের সাইটে যোগাযোগ করুন।"


class ManualBlockScopeChoices(models.TextChoices):
    ALL = "all", "IP + Device + Phone"
    PHONE_ONLY = "phone_only", "Phone Only"
    IP_DEVICE_ONLY = "ip_device_only", "IP + Device Only"


# ----- HOME-PAGE SECTION -----
class HomeSectionTypeChoices(models.TextChoices):
    BUILTIN = "builtin", "Built-in"
    CUSTOM = "custom", "Custom"

class HomeSectionSizeChoices(models.TextChoices):
    COMPACT = "compact", "Compact (small padding)"
    NORMAL = "normal", "Normal"
    SPACIOUS = "spacious", "Spacious (large padding)"

class HomeSectionContentTypeChoices(models.TextChoices):
    BANNER = "banner", "Banner"
    PRODUCT = "product", "Product / Category Wise"

class HomeSectionDesignChoices(models.TextChoices):
    PRODUCT_GRID = "product_grid", "Product Grid (like the main product listing)"
    PRODUCT_SLIDER = "product_slider", "Product Slider (horizontal scroll, like 'Kidz Product')"
    CATEGORY_TILES = "category_tiles", "Category / Sub-category Tiles (shop-by-category)"
    TABBED_PRODUCTS = "tabbed_products", "Category Tabs + Products (tab-to-switch)"
    BESTSELLER_STRIP = "bestseller_strip", "Best Seller / New Arrival Strip (badge grid)"
    BANNER_PRODUCT_COMBO = "banner_product_combo", "Banner + Product Combo (banner beside products)"


class HomeSectionFontChoices(models.TextChoices):
    DEFAULT = "", "Default (site font)"
    SORA = "'Sora', sans-serif", "Sora (site default)"
    HIND_SILIGURI = "'Hind Siliguri', sans-serif", "Hind Siliguri (Bangla)"
    POPPINS = "'Poppins', sans-serif", "Poppins"
    PLAYFAIR = "'Playfair Display', serif", "Playfair Display (elegant serif)"
    MONTSERRAT = "'Montserrat', sans-serif", "Montserrat"
    OSWALD = "'Oswald', sans-serif", "Oswald (condensed/bold)"
    NUNITO = "'Nunito', sans-serif", "Nunito (rounded)"

class CUSTOMIZATION_FIELD_TYPES(models.TextChoices):
    TEXT = "text", "Short text"
    TEXTAREA = "textarea", "Long text"
    SELECT = "select", "Dropdown"
    NUMBER = "number", "Number"


class CUSTOMIZATION_MODE(models.TextChoices):
    OFF = "off", "Off"
    OPTIONAL = "optional", "Optional (customer picks Standard / Customized)"
    MANDATORY = "mandatory", "Mandatory (always customized, asked at checkout)"

class OFFER_GIFT_MODE(models.TextChoices):
    CHOOSE = "choose", "Customer chooses free items from the gift pool"
    AUTO = "auto", "Default gifts are added automatically"

class OFFER_COUNT_MODE(models.TextChoices):
    ALL = "all", "Any qualifying product counts together"
    PRODUCT = "product", "Same product - different variants count together"
    VARIANT = "variant", "Exact same variant only"

class CourierCheckProviderChoices(models.TextChoices):
    BDCOURIER = "bdcourier", "BDCourier"


class CourierLowRatioActionChoices(models.TextChoices):
    OTP = "otp", "Ask for OTP verification"
    WHATSAPP = "whatsapp", "Ask customer to contact support on WhatsApp"


class CourierRetentionUnitChoices(models.TextChoices):
    DAY = "day", "Day(s)"
    WEEK = "week", "Week(s)"
    MONTH = "month", "Month(s)"
    YEAR = "year", "Year(s)"


DEFAULT_COURIER_OTP_MESSAGE = "নিরাপত্তার জন্য অর্ডার করার আগে অনুগ্রহ করে মোবাইল নম্বর OTP দিয়ে ভেরিফাই করুন।"
DEFAULT_COURIER_WHATSAPP_MESSAGE = "দুঃখিত, এই মুহূর্তে অনলাইনে আপনার অর্ডার নেওয়া সম্ভব হচ্ছে না। অনুগ্রহ করে অর্ডার কনফার্ম করতে আমাদের WhatsApp সাপোর্টে যোগাযোগ করুন।"
DEFAULT_COURIER_WHATSAPP_PREFILL = "Hello, I want to place an order. My number: {phone}"


class CourierNoticeClearModeChoices(models.TextChoices):
    MANUAL = "manual", "Only when staff presses Clear"
    ON_OPEN = "on_open", "Automatically when the list is opened"


DEFAULT_COURIER_HARD_BLOCK_MESSAGE = "দুঃখিত, কিছু বিশেষ কারণে এই মুহূর্তে আপনার অনলাইন অর্ডারটি গ্রহণ করা সম্ভব হচ্ছে না। বিস্তারিত জানতে অনুগ্রহ করে আমাদের সাথে যোগাযোগ করুন: {contact}"

# ----- CAMPAIGN (SALE EVENT) SECTION CHOICES -----

class CAMPAIGN_STATUS(models.TextChoices):
    DRAFT = "draft", "Draft"
    UPCOMING = "upcoming", "Upcoming"
    LIVE = "live", "Live"
    ENDED = "ended", "Ended"

class CAMPAIGN_PRICE_SOURCE(models.TextChoices):
    REGULAR = "REGULAR", "Regular price"
    CURRENT = "CURRENT", "Current price (product's own discount price if any)"

class CAMPAIGN_BADGE_MODE(models.TextChoices):
    DISCOUNT_ONLY = "DISCOUNT_ONLY", "Discount only (e.g. 20% OFF)"
    NAME_AND_DISCOUNT = "NAME_AND_DISCOUNT", "Campaign name + discount (e.g. Black Friday · 20% OFF)"

class CAMPAIGN_DISCOUNT_TYPE(models.TextChoices):
    PERCENT = "PERCENT", "Percent"
    FIXED = "FIXED", "Fixed amount (৳)"

class CAMPAIGN_VARIANT_MODE(models.TextChoices):
    ALL_SAME = "ALL_SAME", "Same discount for all variants"
    PER_VARIANT = "PER_VARIANT", "Different discount per variant"

class CAMPAIGN_SWITCH_MODE(models.TextChoices):
    INHERIT = "INHERIT", "Use campaign setting"
    INCLUDE = "INCLUDE", "Include"
    EXCLUDE = "EXCLUDE", "Exclude"

class CAMPAIGN_DELIVERY_MODE(models.TextChoices):
    NORMAL = "NORMAL", "Normal delivery rules"
    CUSTOM = "CUSTOM", "Custom campaign delivery"

class CAMPAIGN_DELIVERY_AMOUNT_SOURCE(models.TextChoices):
    SAME_FOR_ALL = "SAME_FOR_ALL", "Same charge for all campaign products"
    PRODUCT_WISE = "PRODUCT_WISE", "Product-wise charge"

class CAMPAIGN_DELIVERY_BASIS(models.TextChoices):
    PER_ORDER = "PER_ORDER", "One charge per order (highest)"
    PER_PRODUCT = "PER_PRODUCT", "Charge per distinct product (sum)"

class CAMPAIGN_MIXED_CART_DELIVERY(models.TextChoices):
    COMBINED = "COMBINED", "Campaign charge only (normal items add nothing)"
    SEPARATE = "SEPARATE", "Campaign charge + normal charge"


class POPUP_LINK_TYPE(models.TextChoices):
    CAMPAIGN = "CAMPAIGN", "Campaign page"
    PRODUCT = "PRODUCT", "Product page"
    URL = "URL", "Custom URL"
    NONE = "NONE", "No link"

class POPUP_FREQUENCY(models.TextChoices):
    ONCE_PER_SESSION = "ONCE_PER_SESSION", "Once per browser session"
    ONCE_PER_DAY = "ONCE_PER_DAY", "Once per day"
    EVERY_VISIT = "EVERY_VISIT", "Every visit (every page load)"

class POPUP_PAGES(models.TextChoices):
    HOME_ONLY = "HOME_ONLY", "Home page only"
    ALL_PAGES = "ALL_PAGES", "All pages (except cart, checkout, login)"


class DELIVERY_COUNT_MODE(models.TextChoices):
    PRODUCT_WISE = "PRODUCT_WISE", "Per product (each different product adds its own charge)"
    ORDER_WISE = "ORDER_WISE", "Per order (one charge for the whole order)"


class DELIVERY_ORDER_WISE_SOURCE(models.TextChoices):
    GLOBAL = "GLOBAL", "The global charge (ignore product-wise charges)"
    LOWEST = "LOWEST", "The lowest charge among the products in the cart"
    HIGHEST = "HIGHEST", "The highest charge among the products in the cart"



class ORDER_ATTEMPT_STATUS(models.TextChoices):
    PENDING = "pending", "Pending"
    PROGRESS = "progress", "Progress"
    PARTIAL_SUCCESS = "partial_success", "Partial Success"
    CONVERTED = "converted", "Convert Order"
    FAILED = "failed", "Failed"