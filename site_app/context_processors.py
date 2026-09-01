from site_app.models import SiteContent

_DEFAULTS = {
    "brand_name": "PencilWoodBD",
    "brand_short_name": "Pencilwood",
    "dashboard_title": "PencilWoodBD | Online Shopping",
    "brand_website": "www.pencilwoodbd.com",
    "brand_email": "pencilwoodbd@gmail.com",
    "brand_phone": "",
    "invoice_note": "Make all cheques payable to {brand_name}",
}


def brand_context(request):
    """
    Makes brand/site identity fields available in every template that uses
    Django's built-in RequestContext.

    Usage in templates:
        {{ brand_name }}
        {{ brand_short_name }}
        {{ dashboard_title }}
        {{ brand_website }}
        {{ brand_email }}
        {{ brand_phone }}
        {{ invoice_note }}
    """
    site = SiteContent.objects.first()

    def field(name):
        value = getattr(site, name, None) if site else None
        return value if value else _DEFAULTS[name]

    brand_name = field("brand_name")
    invoice_note = field("invoice_note")
    if invoice_note and "{brand_name}" in invoice_note:
        invoice_note = invoice_note.replace("{brand_name}", brand_name)

    return {
        "brand_name": brand_name,
        "brand_short_name": field("brand_short_name"),
        "dashboard_title": field("dashboard_title"),
        "brand_website": field("brand_website"),
        "brand_email": field("brand_email"),
        "brand_phone": field("brand_phone"),
        "invoice_note": invoice_note,
    }