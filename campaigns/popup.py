from urllib.parse import quote

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from pencilwoodbd.choices import CAMPAIGN_STATUS, CATEGORY_PRODUCT_STATUS, POPUP_LINK_TYPE

from .models import CampaignProduct
from .pricing import get_campaign_status
from site_app.models import SitePopup

DEFAULT_CAMPAIGN_PAGE_URL = "/campaign.html?slug={slug}"
DEFAULT_PRODUCT_PAGE_URL = "/product-details.html?slug={slug}"


def campaign_page_url(campaign):
    return getattr(settings, "CAMPAIGN_PAGE_URL", DEFAULT_CAMPAIGN_PAGE_URL).format(slug=quote(campaign.slug))


def product_page_url(product, campaign=None):
    url = getattr(settings, "PRODUCT_PAGE_URL", DEFAULT_PRODUCT_PAGE_URL).format(slug=quote(product.slug or ""))
    if campaign is not None:
        url += ("&" if "?" in url else "?") + "campaign=" + quote(campaign.slug)
    return url


def popup_target_url(popup, now=None):
    now = now or timezone.now()
    kind = popup.link_type
    if kind == POPUP_LINK_TYPE.CAMPAIGN and popup.campaign_id:
        return campaign_page_url(popup.campaign)
    if kind == POPUP_LINK_TYPE.PRODUCT and popup.product_id:
        campaign = None
        if popup.campaign_id and get_campaign_status(popup.campaign, now) == CAMPAIGN_STATUS.LIVE:
            if CampaignProduct.objects.filter(campaign_id=popup.campaign_id, product_id=popup.product_id,
                                              is_active=True).exists():
                campaign = popup.campaign
        return product_page_url(popup.product, campaign)
    if kind == POPUP_LINK_TYPE.URL and (popup.url or "").strip():
        return popup.url.strip()
    return None


def _is_eligible(popup, now):
    if not popup.image_desktop:
        return False
    if popup.campaign_id and get_campaign_status(popup.campaign, now) in (CAMPAIGN_STATUS.DRAFT, CAMPAIGN_STATUS.ENDED):
        return False
    if popup.link_type == POPUP_LINK_TYPE.CAMPAIGN and not popup.campaign_id:
        return False
    if popup.link_type == POPUP_LINK_TYPE.PRODUCT:
        if not popup.product_id or popup.product.status != CATEGORY_PRODUCT_STATUS.ACTIVE:
            return False
    return True


def get_eligible_popup(now=None):
    now = now or timezone.now()
    qs = (
        SitePopup.objects.filter(is_active=True)
        .filter(Q(start_at__isnull=True) | Q(start_at__lte=now))
        .filter(Q(end_at__isnull=True) | Q(end_at__gte=now))
        .select_related("campaign", "product")
        .order_by("-priority", "-id")
    )
    for popup in qs:
        if _is_eligible(popup, now):
            return popup
    return None
