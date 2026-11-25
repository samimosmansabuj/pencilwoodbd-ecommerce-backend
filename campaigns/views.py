import json
from http import HTTPStatus

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from pencilwoodbd.choices import (
    CAMPAIGN_BADGE_MODE,
    CAMPAIGN_DELIVERY_AMOUNT_SOURCE,
    CAMPAIGN_DELIVERY_BASIS,
    CAMPAIGN_DELIVERY_MODE,
    CAMPAIGN_DISCOUNT_TYPE,
    CAMPAIGN_MIXED_CART_DELIVERY,
    CAMPAIGN_PRICE_SOURCE,
    CAMPAIGN_STATUS,
    CAMPAIGN_SWITCH_MODE,
    CAMPAIGN_VARIANT_MODE,
    CATEGORY_PRODUCT_STATUS,
    POPUP_FREQUENCY,
    POPUP_LINK_TYPE,
    POPUP_PAGES,
    USER_TYPE,
)
from product.models import Product
from site_app.bd_districts import BD_DISTRICTS
from site_app.models import SitePopup

from . import dashboard as logic
from .models import Campaign
from .pricing import get_campaign_sales_stats, get_campaign_status
from order.models import OrderItem
from .popup import popup_target_url

STAFF_ROLES = (USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN)


def _bad(message, **extra):
    return JsonResponse({"status": False, "message": message, **extra}, status=HTTPStatus.BAD_REQUEST)


class StaffRequiredMixin(LoginRequiredMixin):
    login_url = "admin_login"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.user_type not in STAFF_ROLES:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.method != "GET":
                return JsonResponse({"status": False, "message": "You do not have permission to do this."}, status=403)
            return HttpResponseForbidden("You do not have permission to open this page.")
        return super().dispatch(request, *args, **kwargs)


STATUS_TABS = [("all", "All"), (CAMPAIGN_STATUS.LIVE, "Live"), (CAMPAIGN_STATUS.UPCOMING, "Upcoming"),
               (CAMPAIGN_STATUS.ENDED, "Ended"), (CAMPAIGN_STATUS.DRAFT, "Draft")]


def _per_page(value, default=10):
    try:
        return max(min(int(value), 100), 1)
    except (TypeError, ValueError):
        return default


class CampaignListView(StaffRequiredMixin, View):
    def get(self, request):
        now = timezone.now()
        search = request.GET.get("q", "").strip()
        status = request.GET.get("status", "all")
        per_page = _per_page(request.GET.get("per_page"))

        base = Campaign.objects.all()
        counts = {"all": base.count()}
        for key, _label in STATUS_TABS[1:]:
            counts[key] = base.filter(logic.status_q(key, now)).count()

        qs = base.annotate(product_count=Count("campaign_products", filter=Q(campaign_products__is_active=True), distinct=True))
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(slug__icontains=search))
        if logic.status_q(status, now) is not None:
            qs = qs.filter(logic.status_q(status, now))
        qs = qs.order_by("-id")

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        ids = [c.id for c in page_obj]
        stats = get_campaign_sales_stats(ids)
        all_orders = {
            r["campaign_id"]: r["n"]
            for r in OrderItem.objects.filter(campaign_id__in=ids).values("campaign_id").annotate(n=Count("order_id", distinct=True))
        }

        rows = []
        for c in page_obj:
            s = stats.get(c.id, {"orders": 0, "units": 0, "revenue": 0})
            rows.append({
                "c": c,
                "status": get_campaign_status(c, now),
                "product_count": c.product_count,
                "orders": s["orders"], "units": s["units"], "revenue": s["revenue"],
                "orders_total": all_orders.get(c.id, 0),
                "orders_url": f"{reverse('order_list')}?campaign={c.id}",
            })

        context = {
            "rows": rows, "campaigns": page_obj, "page_obj": page_obj, "paginator": paginator,
            "counts": counts, "current_status": status, "current_search": search, "current_per_page": str(per_page),
            "status_tabs": STATUS_TABS,
        }
        if request.htmx and request.headers.get("HX-Target") == "campaign-table-wrapper":
            return render(request, "db_campaign/partial/partial_campaign_list.html", context)
        return render(request, "db_campaign/campaign_list.html", context)


def _choices(enum):
    return [{"value": v, "label": str(l)} for v, l in enum.choices]


class CampaignFormView(StaffRequiredMixin, View):
    def get(self, request, pk=None):
        campaign = None
        if pk is not None:
            campaign = get_object_or_404(Campaign, pk=pk)
        return render(request, "db_campaign/campaign_form.html", {
            "campaign": campaign,
            "form_data": logic.campaign_form_data(campaign),
            "bd_districts": BD_DISTRICTS,
            "options": {
                "price_source": _choices(CAMPAIGN_PRICE_SOURCE),
                "badge_mode": _choices(CAMPAIGN_BADGE_MODE),
                "discount_type": _choices(CAMPAIGN_DISCOUNT_TYPE),
                "variant_mode": _choices(CAMPAIGN_VARIANT_MODE),
                "switch_mode": _choices(CAMPAIGN_SWITCH_MODE),
                "delivery_mode": _choices(CAMPAIGN_DELIVERY_MODE),
                "amount_source": _choices(CAMPAIGN_DELIVERY_AMOUNT_SOURCE),
                "basis": _choices(CAMPAIGN_DELIVERY_BASIS),
                "mixed": _choices(CAMPAIGN_MIXED_CART_DELIVERY),
            },
        })


class CampaignSaveView(StaffRequiredMixin, View):
    def post(self, request):
        campaign = None
        if request.POST.get("id"):
            campaign = get_object_or_404(Campaign, pk=request.POST["id"])
        try:
            saved, warnings = logic.save_campaign(request.POST, request.FILES, request.user, campaign)
        except logic.DashboardValidationError as exc:
            flat = [m for msgs in exc.errors.values() for m in msgs]
            return _bad(flat[0] if flat else "Please check the form.", errors=exc.errors,
                        conflicts=[{"campaign": c["campaign_title"], "product": c["product_name"]} for c in exc.conflicts])
        return JsonResponse({
            "status": True,
            "message": "Campaign saved" + (" and published" if saved.is_active else " as a draft"),
            "id": saved.id,
            "is_active": saved.is_active,
            "warnings": warnings,
            "redirect": reverse("campaign_list"),
        })


class CampaignToggleView(StaffRequiredMixin, View):

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        if campaign.is_active and campaign.end_at and campaign.end_at <= timezone.now():
            return _bad("This campaign has already ended, so it is already stopped. Use 'Run again' to set new dates.")
        if campaign.is_active:
            campaign.is_active = False
        else:
            problems = logic.activation_problems(campaign)
            if problems:
                return _bad(" ".join(problems), errors={"products": problems})
            campaign.is_active = True
        campaign.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"status": True, "is_active": campaign.is_active,
                             "campaign_status": get_campaign_status(campaign),
                             "message": "Campaign resumed" if campaign.is_active else "Campaign paused. It is a draft now."})


class CampaignDuplicateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        source = get_object_or_404(Campaign, pk=pk)
        new = logic.duplicate_campaign(source, request.user)
        return JsonResponse({"status": True, "message": "Duplicated as a draft. Set the new dates, then publish.", "id": new.id,
                             "edit_url": reverse("campaign_edit", args=[new.id])})


class CampaignDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        with transaction.atomic():
            logic.delete_campaign_files(campaign)
            campaign.delete()
        return JsonResponse({"status": True, "message": "Campaign deleted"})


class ProductSearchView(StaffRequiredMixin, View):

    def get(self, request):
        exclude = [int(x) for x in request.GET.get("exclude", "").split(",") if x.strip().isdigit()]
        qs = logic.product_search_queryset(request.GET.get("q", ""), exclude)[:20]
        return JsonResponse({"status": True, "products": logic.product_cards(qs)})


def _popup_json(p, request=None):
    return {
        "id": p.id, "title": p.title, "is_active": p.is_active,
        "link_type": p.link_type,
        "campaign": p.campaign_id, "product": p.product_id,
        "product_name": p.product.name if p.product_id else "",
        "url": p.url, "button_text": p.button_text,
        "start_at": logic.local_str(p.start_at), "end_at": logic.local_str(p.end_at),
        "frequency": p.frequency, "pages": p.pages, "priority": p.priority,
        "image_desktop": p.image_desktop.url if p.image_desktop else "",
        "image_mobile": p.image_mobile.url if p.image_mobile else "",
    }


class PopupListView(StaffRequiredMixin, View):
    def get(self, request):
        now = timezone.now()
        search = request.GET.get("q", "").strip()
        status = request.GET.get("status", "all")
        per_page = _per_page(request.GET.get("per_page"))

        qs = SitePopup.objects.select_related("campaign", "product")
        if search:
            qs = qs.filter(title__icontains=search)
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        paginator = Paginator(qs.order_by("-priority", "-id"), per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        rows = []
        for p in page_obj:
            if not p.is_active:
                state = "inactive"
            elif p.start_at and p.start_at > now:
                state = "scheduled"
            elif p.end_at and p.end_at < now:
                state = "ended"
            elif p.campaign_id and get_campaign_status(p.campaign, now) in (CAMPAIGN_STATUS.DRAFT, CAMPAIGN_STATUS.ENDED):
                state = "skipped"
            else:
                state = "showing"
            rows.append({"p": p, "state": state, "target": popup_target_url(p, now)})

        context = {
            "rows": rows, "popups": page_obj, "page_obj": page_obj, "paginator": paginator,
            "current_status": status, "current_search": search, "current_per_page": str(per_page),
            "status_tabs": [("all", "All"), ("active", "Active"), ("inactive", "Inactive")],
            "counts": {"all": SitePopup.objects.count(), "active": SitePopup.objects.filter(is_active=True).count(),
                       "inactive": SitePopup.objects.filter(is_active=False).count()},
        }
        if request.htmx and request.headers.get("HX-Target") == "popup-table-wrapper":
            return render(request, "db_popup/partial/partial_popup_list.html", context)

        context.update({
            "campaign_options": [{"id": c.id, "title": c.title, "status": get_campaign_status(c, now)}
                                 for c in Campaign.objects.order_by("-id")],
            "link_types": _choices(POPUP_LINK_TYPE),
            "frequencies": _choices(POPUP_FREQUENCY),
            "page_choices": _choices(POPUP_PAGES),
        })
        return render(request, "db_popup/popup_list.html", context)


class PopupDataView(StaffRequiredMixin, View):
    def get(self, request, pk):
        popup = get_object_or_404(SitePopup.objects.select_related("product"), pk=pk)
        return JsonResponse({"status": True, "popup": _popup_json(popup)})


class PopupSaveView(StaffRequiredMixin, View):
    def post(self, request):
        d = request.POST
        popup = get_object_or_404(SitePopup, pk=d["id"]) if d.get("id") else SitePopup()

        title = (d.get("title") or "").strip()
        if not title:
            return _bad("Popup title is required")
        link_type = d.get("link_type") if d.get("link_type") in POPUP_LINK_TYPE.values else POPUP_LINK_TYPE.NONE
        frequency = d.get("frequency") if d.get("frequency") in POPUP_FREQUENCY.values else POPUP_FREQUENCY.ONCE_PER_SESSION
        pages = d.get("pages") if d.get("pages") in POPUP_PAGES.values else POPUP_PAGES.HOME_ONLY

        campaign = product = None
        url = ""
        if link_type == POPUP_LINK_TYPE.CAMPAIGN:
            campaign = Campaign.objects.filter(pk=d.get("campaign") or 0).first()
            if campaign is None:
                return _bad("Choose the campaign this popup opens")
        elif link_type == POPUP_LINK_TYPE.PRODUCT:
            product = Product.objects.filter(pk=d.get("product") or 0).first()
            if product is None:
                return _bad("Choose the product this popup opens")
            campaign = Campaign.objects.filter(pk=d.get("campaign") or 0).first()
        elif link_type == POPUP_LINK_TYPE.URL:
            url = (d.get("url") or "").strip()
            if not url:
                return _bad("Enter the web address the popup opens")
            if not (url.startswith(("http://", "https://", "/"))):
                return _bad("The web address must start with https:// (another website) or / (a page of this store)")

        start_at, end_at = logic.parse_local_dt(d.get("start_at")), logic.parse_local_dt(d.get("end_at"))
        if start_at and end_at and end_at <= start_at:
            return _bad("End time must be after the start time")
        try:
            priority = int(d.get("priority") or 0)
        except ValueError:
            return _bad("Priority must be a whole number")

        desktop, mobile = request.FILES.get("image_desktop"), request.FILES.get("image_mobile")
        if not popup.pk and not desktop:
            return _bad("The desktop image is required")
        try:
            if desktop:
                desktop = logic._prepare_image(desktop, 1600)
            if mobile:
                mobile = logic._prepare_image(mobile, 1000)
        except ValidationError as exc:
            return _bad(exc.messages[0])

        popup.title = title[:120]
        popup.link_type, popup.campaign, popup.product, popup.url = link_type, campaign, product, url
        popup.button_text = (d.get("button_text") or "").strip()[:60]
        popup.is_active = d.get("is_active") in ("1", "true", "on")
        popup.start_at, popup.end_at = start_at, end_at
        popup.frequency, popup.pages, popup.priority = frequency, pages, priority
        if desktop:
            popup.image_desktop = desktop
        if mobile:
            popup.image_mobile = mobile
        elif d.get("clear_image_mobile") in ("1", "true"):
            popup.image_mobile = None
        popup.save()
        return JsonResponse({"status": True, "message": "Popup saved", "id": popup.id})


class PopupToggleView(StaffRequiredMixin, View):
    def post(self, request, pk):
        popup = get_object_or_404(SitePopup, pk=pk)
        popup.is_active = not popup.is_active
        popup.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"status": True, "is_active": popup.is_active})


class PopupDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(SitePopup, pk=pk).delete()
        return JsonResponse({"status": True, "message": "Popup deleted"})