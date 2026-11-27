from pencilwoodbd.choices import PRODUCT_MEDIA_ROLE

from .pricing import get_campaign_status


def _abs(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


def campaign_public_dict(campaign, request, now):
    return {
        "id": campaign.id,
        "slug": campaign.slug,
        "title": campaign.title,
        "short_description": campaign.short_description,
        "thumbnail": _abs(request, campaign.thumbnail),
        "banner_desktop": _abs(request, campaign.banner_desktop),
        "banner_mobile": _abs(request, campaign.banner_mobile),
        "show_in_slider": campaign.show_in_slider,
        "price_surfaces": list(campaign.price_surfaces or []),
        "hero_title": campaign.hero_title,
        "hero_button_text": campaign.hero_button_text,
        "status": get_campaign_status(campaign, now),
        "start_at": campaign.start_at.isoformat(),
        "end_at": campaign.end_at.isoformat(),
        "server_now": now.isoformat(),
    }


def campaign_detail_dict(campaign, request, now):
    data = campaign_public_dict(campaign, request, now)
    data.update({
        "hero_title": campaign.hero_title,
        "hero_subtitle": campaign.hero_subtitle,
        "hero_button_text": campaign.hero_button_text,
        "badge_label": campaign.badge_label,
    })
    return data


def primary_image_url(product):
    images = list(product.images.all())
    primary = next((i for i in images if i.role == PRODUCT_MEDIA_ROLE.PRIMARY and i.variant_id is None), None)
    if primary and primary.image:
        return primary.image.url
    first = next((i for i in images if i.variant_id is None), None) or (images[0] if images else None)
    if first and first.image:
        return first.image.url
    return None
