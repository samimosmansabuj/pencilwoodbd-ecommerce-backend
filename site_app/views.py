from http import HTTPStatus
from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from product.models import ProductVideo
from site_app.models import ShowcaseMedia, HomeSection, About_WhyChooseUs

import json as pyjson

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce, TruncDate
from django.conf import settings

from pencilwoodbd.extra_module import resize_to_fixed, parse_int, parse_delivery_charge_payload
from pencilwoodbd.choices import USER_TYPE, STATUS

from .bd_districts import BD_DISTRICTS, SYSTEM_DEFAULT_DELIVERY_CHARGE
from .models import (
    HomeSlider, SiteDeliveryChargeConfig, FooterTagLink, SocialLink, NavMenuLink,
    NewsFeed, Todo, Reminder, MaintenanceCost, DailyProfit, InvoiceColorConfig,
)
from authentication.models import CustomUser
from order.models import Order, OrderRequest
from order.views import OrderDetailView, OrderRequestDetailView

class ShowcaseMediaView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        items = ShowcaseMedia.objects.select_related("product_video", "product_video__product").order_by("sort_order", "-id")
        product_videos = ProductVideo.objects.select_related("product").order_by("-id")[:200]

        context = {
            "items": items,
            "product_videos": product_videos,
        }

        if request.htmx:
            return render(request, "db_showcase/partial/partial_showcase_list.html", context)

        return render(request, "db_showcase/showcase_list.html", context)

    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST
                item_id = data.get("item_id")

                title = data.get("title", "").strip()
                subtitle = data.get("subtitle", "").strip()
                media_type = data.get("media_type", "").strip()
                sort_order = data.get("sort_order") or 0

                if not title:
                    return JsonResponse({"status": False, "message": "Title is required"}, status=HTTPStatus.BAD_REQUEST)

                valid_types = [c[0] for c in ShowcaseMedia.MediaType.choices]
                if media_type not in valid_types:
                    return JsonResponse({"status": False, "message": "Invalid media type"}, status=HTTPStatus.BAD_REQUEST)

                image = request.FILES.get("image")
                video_file = request.FILES.get("video_file")
                video_url = data.get("video_url", "").strip()
                poster_image = request.FILES.get("poster_image")
                product_video_id = data.get("product_video_id") or None

                if media_type == ShowcaseMedia.MediaType.IMAGE and not image and not item_id:
                    return JsonResponse({"status": False, "message": "Image is required for Image type"}, status=HTTPStatus.BAD_REQUEST)
                if media_type == ShowcaseMedia.MediaType.UPLOADED_VIDEO and not video_file and not item_id:
                    return JsonResponse({"status": False, "message": "Video file is required for Uploaded Video type"}, status=HTTPStatus.BAD_REQUEST)
                if media_type == ShowcaseMedia.MediaType.EXTERNAL_LINK and not video_url and not item_id:
                    return JsonResponse({"status": False, "message": "Video link is required for External Link type"}, status=HTTPStatus.BAD_REQUEST)
                if media_type == ShowcaseMedia.MediaType.PRODUCT_VIDEO and not product_video_id and not item_id:
                    return JsonResponse({"status": False, "message": "Please select a product video"}, status=HTTPStatus.BAD_REQUEST)

                if item_id:
                    item = get_object_or_404(ShowcaseMedia, id=item_id)
                else:
                    item = ShowcaseMedia()

                item.title = title
                item.subtitle = subtitle or None
                item.media_type = media_type
                item.sort_order = int(sort_order) if str(sort_order).isdigit() else 0

                if image:
                    item.image = image
                if video_file:
                    item.video_file = video_file
                if video_url:
                    item.video_url = video_url
                if poster_image:
                    item.poster_image = poster_image
                if product_video_id:
                    item.product_video_id = int(product_video_id)

                item.save()

                msg = "Item updated successfully" if item_id else "Item added successfully"
                return JsonResponse({"status": True, "message": msg}, status=HTTPStatus.OK if item_id else HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def get_showcase_item(request, id):
    try:
        item = get_object_or_404(ShowcaseMedia, id=id)
        return JsonResponse({
            "status": True,
            "item": {
                "id": item.id,
                "title": item.title,
                "subtitle": item.subtitle or "",
                "media_type": item.media_type,
                "image": item.image.url if item.image else None,
                "video_file": item.video_file.url if item.video_file else None,
                "video_url": item.video_url or "",
                "poster_image": item.poster_image.url if item.poster_image else None,
                "product_video_id": item.product_video_id,
                "sort_order": item.sort_order,
                "is_active": item.is_active,
            },
        }, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_showcase_item(request, id):
    if request.method == "DELETE":
        try:
            item = get_object_or_404(ShowcaseMedia, id=id)
            item.delete()
            return JsonResponse({"status": True, "message": "Item deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_showcase_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        item = get_object_or_404(ShowcaseMedia, id=id)
        item.is_active = request.POST.get("is_active") == "true"
        item.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Status updated", "is_active": item.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    


# HOME SECTION (Section-level ON/OFF switch for homepage blocks)
class HomeSectionManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        items = HomeSection.objects.all()
        context = {"items": items}

        if request.htmx:
            return render(request, "db_home_sections/partial/partial_home_section_list.html", context)

        return render(request, "db_home_sections/home_section_list.html", context)

    def post(self, request):
        try:
            data = request.POST
            item_id = data.get("item_id")

            section_key = data.get("section_key", "").strip()
            admin_label = data.get("admin_label", "").strip()
            section_type = data.get("section_type", "custom").strip()
            heading = data.get("heading", "").strip()
            subheading = data.get("subheading", "").strip()
            body_html = data.get("body_html", "").strip()
            button_text = data.get("button_text", "").strip()
            button_url = data.get("button_url", "").strip()
            size = data.get("size", "normal").strip()
            min_height_px = data.get("min_height_px", "").strip()
            sort_order = data.get("sort_order") or 0
            is_active = data.get("is_active") == "on"
            image = request.FILES.get("image")

            if not admin_label:
                return JsonResponse({"status": False, "message": "Admin label is required"}, status=HTTPStatus.BAD_REQUEST)

            if item_id:
                item = get_object_or_404(HomeSection, id=item_id)
            else:
                if not section_key:
                    return JsonResponse({"status": False, "message": "Section key is required"}, status=HTTPStatus.BAD_REQUEST)
                if HomeSection.objects.filter(section_key=section_key).exists():
                    return JsonResponse({"status": False, "message": "This section key already exists"}, status=HTTPStatus.BAD_REQUEST)
                item = HomeSection()
                item.section_key = section_key

            item.admin_label = admin_label
            item.section_type = section_type if section_type in ("builtin", "custom") else "custom"
            item.heading = heading or None
            item.subheading = subheading or None
            item.body_html = body_html or None
            item.button_text = button_text or None
            item.button_url = button_url or None
            item.size = size if size in ("compact", "normal", "spacious") else "normal"
            item.min_height_px = int(min_height_px) if min_height_px.isdigit() else None
            item.sort_order = int(sort_order) if str(sort_order).isdigit() else 0
            item.is_active = is_active

            if image:
                item.image = image

            item.save()

            msg = "Section updated successfully" if item_id else "Section added successfully"
            return JsonResponse({"status": True, "message": msg}, status=HTTPStatus.OK if item_id else HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def get_home_section(request, id):
    try:
        item = get_object_or_404(HomeSection, id=id)
        return JsonResponse({
            "status": True,
            "item": {
                "id": item.id,
                "section_key": item.section_key,
                "admin_label": item.admin_label,
                "section_type": item.section_type,
                "heading": item.heading or "",
                "subheading": item.subheading or "",
                "body_html": item.body_html or "",
                "image": item.image.url if item.image else None,
                "button_text": item.button_text or "",
                "button_url": item.button_url or "",
                "size": item.size,
                "min_height_px": item.min_height_px or "",
                "sort_order": item.sort_order,
                "is_active": item.is_active,
            },
        }, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_home_section(request, id):
    if request.method == "DELETE":
        try:
            item = get_object_or_404(HomeSection, id=id)
            if item.section_type == "builtin":
                return JsonResponse({"status": False, "message": "Built-in sections cannot be deleted, only turned off."}, status=HTTPStatus.BAD_REQUEST)
            item.delete()
            return JsonResponse({"status": True, "message": "Section deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_home_section_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        item = get_object_or_404(HomeSection, id=id)
        item.is_active = request.POST.get("is_active") == "true"
        item.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Status updated", "is_active": item.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


# WHY CHOOSE US CARDS (content inside the "Why Choose Pencilwood" section)
class WhyChooseUsManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        items = About_WhyChooseUs.objects.all()
        context = {"items": items}

        if request.htmx:
            return render(request, "db_home_sections/partial/partial_why_choose_list.html", context)

        return render(request, "db_home_sections/why_choose_list.html", context)

    def post(self, request):
        try:
            data = request.POST
            item_id = data.get("item_id")

            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            icon = data.get("icon", "").strip()
            sort_order = data.get("sort_order") or 0
            is_active = data.get("is_active") == "on"

            if not title:
                return JsonResponse({"status": False, "message": "Title is required"}, status=HTTPStatus.BAD_REQUEST)

            if item_id:
                item = get_object_or_404(About_WhyChooseUs, id=item_id)
            else:
                item = About_WhyChooseUs()

            item.title = title
            item.description = description or None
            item.icon = icon or None
            item.sort_order = int(sort_order) if str(sort_order).isdigit() else 0
            item.is_active = is_active
            item.save()

            msg = "Card updated successfully" if item_id else "Card added successfully"
            return JsonResponse({"status": True, "message": msg}, status=HTTPStatus.OK if item_id else HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def get_why_choose_item(request, id):
    try:
        item = get_object_or_404(About_WhyChooseUs, id=id)
        return JsonResponse({
            "status": True,
            "item": {
                "id": item.id,
                "title": item.title,
                "description": item.description or "",
                "icon": item.icon or "",
                "sort_order": item.sort_order,
                "is_active": item.is_active,
            },
        }, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_why_choose_item(request, id):
    if request.method == "DELETE":
        try:
            item = get_object_or_404(About_WhyChooseUs, id=id)
            item.delete()
            return JsonResponse({"status": True, "message": "Card deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_why_choose_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        item = get_object_or_404(About_WhyChooseUs, id=id)
        item.is_active = request.POST.get("is_active") == "true"
        item.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Status updated", "is_active": item.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)

# Dashboard (staff/admin) site-settings views

HERO_SLIDER_LIMIT = getattr(settings, "HERO_SLIDER_MAX_ACTIVE", 5)


class SliderView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        # Manual sliders + product-linked sliders, all in ONE list
        sliders = HomeSlider.objects.select_related("product").order_by("-id")
        active_count = sliders.filter(is_active=True).count()

        context = {
            "sliders": sliders,
            "active_count": active_count,
            "max_active": HERO_SLIDER_LIMIT,
            "limit_reached": active_count >= HERO_SLIDER_LIMIT,
        }

        if request.htmx:
            return render(request, "db_slider/partial/partial_slider_list.html", context)

        return render(request, "db_slider/slider_list.html", context)

    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST
                slider_id = data.get("slider_id")

                title = data.get("title", "").strip()
                url = data.get("url", "").strip()
                button_name = data.get("button_name", "").strip()
                image = request.FILES.get("image")

                if not title:
                    return JsonResponse({"status": False, "message": "Slider name is required"}, status=HTTPStatus.BAD_REQUEST)

                if slider_id:
                    slider = get_object_or_404(HomeSlider, id=slider_id, product__isnull=True)
                    slider.title = title
                    slider.url = url or None
                    slider.button_name = button_name or None
                    if image:  # only one image per slider — new upload auto-replaces old
                        slider.image = resize_to_fixed(image, settings.HERO_SLIDER_SIZE)
                    slider.save()
                    return JsonResponse({"status": True, "message": "Slider updated successfully"}, status=HTTPStatus.OK)

                if not image:
                    return JsonResponse({"status": False, "message": "Slider image is required"}, status=HTTPStatus.BAD_REQUEST)

                HomeSlider.objects.create(
                    title=title,
                    url=url or None,
                    button_name=button_name or None,
                    image=resize_to_fixed(image, settings.HERO_SLIDER_SIZE),
                    is_active=False,  # admin must explicitly activate
                )
                return JsonResponse({"status": True, "message": "Slider added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def get_slider(request, id):
    try:
        slider = get_object_or_404(HomeSlider, id=id)
        return JsonResponse({
            "status": True,
            "slider": {
                "id": slider.id,
                "title": slider.title,
                "url": slider.url,
                "button_name": slider.button_name,
                "image": slider.image.url if slider.image else None,
                "is_product": slider.product_id is not None,
            },
        }, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_slider(request, id):
    if request.method == "DELETE":
        try:
            slider = get_object_or_404(HomeSlider, id=id, product__isnull=True)  # can't delete product-linked ones from here
            slider.delete()
            return JsonResponse({"status": True, "message": "Slider deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_slider_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)

    try:
        slider = get_object_or_404(HomeSlider, id=id)
        want_active = request.POST.get("is_active") == "true"

        if want_active and not slider.is_active:
            active_count = HomeSlider.objects.filter(is_active=True).count()
            if active_count >= HERO_SLIDER_LIMIT:
                return JsonResponse({
                    "status": False,
                    "message": f"You can only have {HERO_SLIDER_LIMIT} active sliders at a time. Turn one off first."
                }, status=HTTPStatus.BAD_REQUEST)

        slider.is_active = want_active
        slider.save(update_fields=["is_active"])

        new_active_count = HomeSlider.objects.filter(is_active=True).count()

        return JsonResponse({
            "status": True,
            "message": "Slider status updated",
            "is_active": slider.is_active,
            "active_count": new_active_count,
            "limit_reached": new_active_count >= HERO_SLIDER_LIMIT,
        }, status=HTTPStatus.OK)

    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    
# ------------------Product--------


class DeliveryChargeSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"
 
    def _can_manage(self, request):
        return request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]
 
    def get(self, request):
        config = SiteDeliveryChargeConfig.get_solo()
 
        context = {
            "bd_districts": BD_DISTRICTS,
            "existing_delivery_charge_json": pyjson.dumps(config.area_and_charge or {}),
            "system_default_charge": SYSTEM_DEFAULT_DELIVERY_CHARGE,
        }
 
        if request.htmx:
            return render(request, "db_settings/partial/partial_delivery_charge_settings.html", context)
 
        return render(request, "db_settings/delivery_charge_settings.html", context)
 
    def post(self, request):
        if not self._can_manage(request):
            messages.error(request, "You don't have permission to change global delivery charges.")
            return redirect("delivery_charge_settings")
 
        area_and_charge, has_charge, _delivery_charge_cost = parse_delivery_charge_payload(request)

        config = SiteDeliveryChargeConfig.get_solo()
        config.area_and_charge = area_and_charge or {}
        config.save()
 
        messages.success(request, "Global delivery charge settings updated successfully.")
        return redirect("delivery_charge_settings")

# ------------------Attribute--------


class FooterLinkManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        links = FooterTagLink.objects.all()
        context = {"links": links}

        if request.htmx:
            return render(request, "db_settings/partial/partial_footer_link_list.html", context)

        return render(request, "db_settings/footer_links.html", context)

    def post(self, request):
        try:
            data = request.POST
            link_id = data.get("link_id")

            name = data.get("name", "").strip()
            url = data.get("url", "").strip()
            sort_order = parse_int(data.get("sort_order"), 0)
            is_active = data.get("is_active") == "on"

            if not name:
                return JsonResponse({"status": False, "message": "Name is required"}, status=HTTPStatus.BAD_REQUEST)

            if link_id:
                link = get_object_or_404(FooterTagLink, id=link_id)
                link.name = name
                link.url = url or None
                link.sort_order = sort_order
                link.is_active = is_active
                link.save()
                return JsonResponse({"status": True, "message": "Footer link updated successfully"}, status=HTTPStatus.OK)

            FooterTagLink.objects.create(
                name=name, url=url or None, sort_order=sort_order, is_active=is_active,
            )
            return JsonResponse({"status": True, "message": "Footer link added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_footer_link(request, id):
    if request.method == "DELETE":
        try:
            link = get_object_or_404(FooterTagLink, id=id)
            link.delete()
            return JsonResponse({"status": True, "message": "Footer link deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_footer_link_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        link = get_object_or_404(FooterTagLink, id=id)
        link.is_active = request.POST.get("is_active") == "true"
        link.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Footer link status updated", "is_active": link.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


# ------------------Site Content: Social Links--------


class SocialLinkManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        links = SocialLink.objects.all()
        context = {"links": links}

        if request.htmx:
            return render(request, "db_settings/partial/partial_social_link_list.html", context)

        return render(request, "db_settings/social_links.html", context)

    def post(self, request):
        try:
            data = request.POST
            link_id = data.get("link_id")

            name = data.get("name", "").strip()
            icon = data.get("icon", "").strip()
            url = data.get("url", "").strip()
            sort_order = parse_int(data.get("sort_order"), 0)
            is_active = data.get("is_active") == "on"

            if not name:
                return JsonResponse({"status": False, "message": "Name is required"}, status=HTTPStatus.BAD_REQUEST)

            if link_id:
                link = get_object_or_404(SocialLink, id=link_id)
                link.name = name
                link.icon = icon or None
                link.url = url or None
                link.sort_order = sort_order
                link.is_active = is_active
                link.save()
                return JsonResponse({"status": True, "message": "Social link updated successfully"}, status=HTTPStatus.OK)

            SocialLink.objects.create(
                name=name, icon=icon or None, url=url or None,
                sort_order=sort_order, is_active=is_active,
            )
            return JsonResponse({"status": True, "message": "Social link added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_social_link(request, id):
    if request.method == "DELETE":
        try:
            link = get_object_or_404(SocialLink, id=id)
            link.delete()
            return JsonResponse({"status": True, "message": "Social link deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_social_link_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        link = get_object_or_404(SocialLink, id=id)
        link.is_active = request.POST.get("is_active") == "true"
        link.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Social link status updated", "is_active": link.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


# ------------------Site Content: Navbar / Subnav Menu Links--------


class NavMenuManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        links = NavMenuLink.objects.all()
        context = {"links": links}

        if request.htmx:
            return render(request, "db_settings/partial/partial_nav_menu_list.html", context)

        return render(request, "db_settings/nav_menu.html", context)

    def post(self, request):
        try:
            data = request.POST
            link_id = data.get("link_id")

            name = data.get("name", "").strip()
            url = data.get("url", "").strip()
            sort_order = parse_int(data.get("sort_order"), 0)
            open_new_tab = data.get("open_new_tab") == "on"
            is_active = data.get("is_active") == "on"

            if not name:
                return JsonResponse({"status": False, "message": "Name is required"}, status=HTTPStatus.BAD_REQUEST)

            if link_id:
                link = get_object_or_404(NavMenuLink, id=link_id)
                link.name = name
                link.url = url or "#"
                link.sort_order = sort_order
                link.open_new_tab = open_new_tab
                link.is_active = is_active
                link.save()
                return JsonResponse({"status": True, "message": "Menu link updated successfully"}, status=HTTPStatus.OK)

            NavMenuLink.objects.create(
                name=name, url=url or "#", sort_order=sort_order,
                open_new_tab=open_new_tab, is_active=is_active,
            )
            return JsonResponse({"status": True, "message": "Menu link added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_nav_menu_link(request, id):
    if request.method == "DELETE":
        try:
            link = get_object_or_404(NavMenuLink, id=id)
            link.delete()
            return JsonResponse({"status": True, "message": "Menu link deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_nav_menu_link_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        link = get_object_or_404(NavMenuLink, id=id)
        link.is_active = request.POST.get("is_active") == "true"
        link.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "Menu link status updated", "is_active": link.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


# ------------------Site Content: News Feed (Top Bar Ticker)--------


class NewsFeedManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        items = NewsFeed.objects.all()
        context = {"items": items}

        if request.htmx:
            return render(request, "db_settings/partial/partial_news_feed_list.html", context)

        return render(request, "db_settings/news_feed.html", context)

    def post(self, request):
        try:
            data = request.POST
            item_id = data.get("item_id")

            news = data.get("news", "").strip()
            url = data.get("url", "").strip()
            sort_order = parse_int(data.get("sort_order"), 0)
            is_active = data.get("is_active") == "on"

            if not news:
                return JsonResponse({"status": False, "message": "News text is required"}, status=HTTPStatus.BAD_REQUEST)

            if item_id:
                item = get_object_or_404(NewsFeed, id=item_id)
                item.news = news
                item.url = url or None
                item.sort_order = sort_order
                item.is_active = is_active
                item.save()
                return JsonResponse({"status": True, "message": "News feed item updated successfully"}, status=HTTPStatus.OK)

            NewsFeed.objects.create(
                news=news, url=url or None, sort_order=sort_order, is_active=is_active,
            )
            return JsonResponse({"status": True, "message": "News feed item added successfully"}, status=HTTPStatus.CREATED)

        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def delete_news_feed(request, id):
    if request.method == "DELETE":
        try:
            item = get_object_or_404(NewsFeed, id=id)
            item.delete()
            return JsonResponse({"status": True, "message": "News feed item deleted successfully"}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)


@login_required(login_url="admin_login")
def toggle_news_feed_active(request, id):
    if request.method != "POST":
        return JsonResponse({"status": False, "message": "Invalid request"}, status=HTTPStatus.BAD_REQUEST)
    try:
        item = get_object_or_404(NewsFeed, id=id)
        item.is_active = request.POST.get("is_active") == "true"
        item.save(update_fields=["is_active"])
        return JsonResponse({"status": True, "message": "News feed status updated", "is_active": item.is_active}, status=HTTPStatus.OK)
    except Exception as e:
        return JsonResponse({"status": False, "message": str(e)}, status=HTTPStatus.BAD_REQUEST)



STAFF_TYPES = ['staff', 'admin', 'super_admin']


# ----------------- TODO -----------------


class TodoListView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_todo/todo_list.html"

    def get(self, request):
        todos = Todo.objects.select_related('assigned_to', 'created_by').all()
        priority = request.GET.get('priority')
        if priority:
            todos = todos.filter(priority=priority)
        status = request.GET.get('status')
        if status == 'complete':
            todos = todos.filter(is_complete=True)
        elif status == 'pending':
            todos = todos.filter(is_complete=False)
        search = request.GET.get('search')
        if search:
            todos = todos.filter(title__icontains=search)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        if start_date:
            todos = todos.filter(due_date__gte=start_date)
        if end_date:
            todos = todos.filter(due_date__lte=end_date)

        context = {
            "todos": todos,
            "staff_list": CustomUser.objects.filter(user_type__in=STAFF_TYPES),
            "priority_choices": Todo.Priority.choices,
        }
        if request.htmx:
            return render(request, "db_todo/partial/partial_todo_list.html", context)
        return render(request, self.template_name, context)


class TodoCreateUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk=None):
        todo = get_object_or_404(Todo, pk=pk) if pk else Todo()
        todo.title = request.POST.get('title')
        todo.description = request.POST.get('description')
        todo.priority = request.POST.get('priority', Todo.Priority.MEDIUM)
        todo.due_date = request.POST.get('due_date') or None
        todo.assigned_to_id = request.POST.get('assigned_to') or None
        if not pk:
            todo.created_by = request.user
        todo.save()
        messages.success(request, "Todo saved successfully.")
        return self._list_response(request)

    def _list_response(self, request):
        if request.htmx:
            todos = Todo.objects.select_related('assigned_to', 'created_by').all()
            return render(request, "db_todo/partial/partial_todo_list.html", {
                "todos": todos,
                "staff_list": CustomUser.objects.filter(user_type__in=STAFF_TYPES),
                "priority_choices": Todo.Priority.choices,
            })
        return redirect('todo_list')


class TodoToggleCompleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        todo = get_object_or_404(Todo, pk=pk)
        todo.is_complete = not todo.is_complete
        todo.save(update_fields=['is_complete'])
        return TodoCreateUpdateView()._list_response(request)


class TodoDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        get_object_or_404(Todo, pk=pk).delete()
        messages.success(request, "Todo deleted.")
        return TodoCreateUpdateView()._list_response(request)


# ----------------- REMINDER -----------------


class ReminderListView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_reminder/reminder_list.html"

    def get(self, request):
        reminders = Reminder.objects.select_related('order', 'order_request', 'assigned_to').all()
        status = request.GET.get('status')
        if status == 'complete':
            reminders = reminders.filter(is_complete=True)
        elif status == 'pending':
            reminders = reminders.filter(is_complete=False)
        assigned_to = request.GET.get('assigned_to')
        if assigned_to:
            reminders = reminders.filter(assigned_to_id=assigned_to)

        context = {
            "reminders": reminders,
            "staff_list": CustomUser.objects.filter(user_type__in=STAFF_TYPES),
        }
        if request.htmx:
            return render(request, "db_reminder/partial/partial_reminder_list.html", context)
        return render(request, self.template_name, context)


class ReminderCreateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        reminder = Reminder()
        order_id = request.POST.get('order_id')
        order_request_id = request.POST.get('order_request_id')
        if order_id:
            reminder.order = get_object_or_404(Order, pk=order_id)
        if order_request_id:
            reminder.order_request = get_object_or_404(OrderRequest, pk=order_request_id)
        reminder.note = request.POST.get('note')
        reminder.remind_date = request.POST.get('remind_date')
        reminder.remind_time = request.POST.get('remind_time')
        reminder.assigned_to_id = request.POST.get('assigned_to') or None
        reminder.created_by = request.user
        reminder.save()
        messages.success(request, "Reminder added.")

        if order_id:
            return OrderDetailView().get(request, id=order_id)
        if order_request_id:
            return OrderRequestDetailView().get(request, id=order_request_id)
        return redirect('reminder_list')


class ReminderToggleCompleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        reminder = get_object_or_404(Reminder, pk=pk)
        reminder.is_complete = not reminder.is_complete
        reminder.save(update_fields=['is_complete'])
        return self._list_response(request)

    def _list_response(self, request):
        if request.htmx:
            reminders = Reminder.objects.select_related('order', 'order_request', 'assigned_to').all()
            return render(request, "db_reminder/partial/partial_reminder_list.html", {
                "reminders": reminders,
                "staff_list": CustomUser.objects.filter(user_type__in=STAFF_TYPES),
            })
        return redirect('reminder_list')


class ReminderDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        get_object_or_404(Reminder, pk=pk).delete()
        messages.success(request, "Reminder deleted.")
        return ReminderToggleCompleteView()._list_response(request)


# ----------------- FINANCE -----------------


class MaintenanceCostListView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_finance/maintenance_cost_list.html"

    def get(self, request):
        costs = MaintenanceCost.objects.select_related('created_by').all()
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        if start_date:
            costs = costs.filter(date__gte=start_date)
        if end_date:
            costs = costs.filter(date__lte=end_date)
        search = request.GET.get('search')
        if search:
            costs = costs.filter(name__icontains=search)

        context = {
            "costs": costs,
            "category_choices": MaintenanceCost.Category.choices,
            "payment_method_choices": MaintenanceCost.PaymentMethod.choices,
        }
        if request.htmx:
            return render(request, "db_finance/partial/partial_maintenance_cost_list.html", context)
        return render(request, self.template_name, context)


class MaintenanceCostCreateUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk=None):
        cost = get_object_or_404(MaintenanceCost, pk=pk) if pk else MaintenanceCost()
        cost.name = request.POST.get('name')
        cost.amount = request.POST.get('amount')
        cost.date = request.POST.get('date')
        cost.category = request.POST.get('category') or MaintenanceCost.Category.OTHERS
        cost.vendor_name = request.POST.get('vendor_name') or None
        cost.payment_method = request.POST.get('payment_method') or None
        cost.reference_number = request.POST.get('reference_number') or None
        cost.note = request.POST.get('note')
        if not pk:
            cost.created_by = request.user
        cost.save()  # signal auto-links to that day's DailyProfit
        messages.success(request, "Maintenance cost saved.")
        return self._list_response(request)

    def _list_response(self, request):
        if request.htmx:
            costs = MaintenanceCost.objects.select_related('created_by').all()
            return render(request, "db_finance/partial/partial_maintenance_cost_list.html", {
                "costs": costs,
                "category_choices": MaintenanceCost.Category.choices,
                "payment_method_choices": MaintenanceCost.PaymentMethod.choices,
            })
        return redirect('maintenance_cost_list')


class MaintenanceCostDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        get_object_or_404(MaintenanceCost, pk=pk).delete()
        messages.success(request, "Maintenance cost deleted.")
        return MaintenanceCostCreateUpdateView()._list_response(request)


class DailyProfitListView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_finance/daily_profit_list.html"

    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        # ---- Booked Revenue: by order creation date ----
        booked_qs = Order.objects.all()
        if start_date:
            booked_qs = booked_qs.filter(created_at__date__gte=start_date)
        if end_date:
            booked_qs = booked_qs.filter(created_at__date__lte=end_date)

        booked_rows = (
            booked_qs
            .annotate(order_date=TruncDate('created_at'))
            .values('order_date')
            .annotate(
                booked_revenue=Coalesce(
                    Sum(F('order_items__discount_price') * F('order_items__quantity') + F('shipping_total')),
                    Value(0), output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )
        booked_map = {row['order_date']: row['booked_revenue'] for row in booked_rows}

        # ---- Realized Revenue: by delivered_at date (actual cash) ----
        realized_qs = Order.objects.filter(status=STATUS.DELIVERED, delivered_at__isnull=False)
        if start_date:
            realized_qs = realized_qs.filter(delivered_at__date__gte=start_date)
        if end_date:
            realized_qs = realized_qs.filter(delivered_at__date__lte=end_date)

        realized_rows = (
            realized_qs
            .annotate(delivered_date=TruncDate('delivered_at'))
            .values('delivered_date')
            .annotate(
                realized_revenue=Coalesce(
                    Sum(F('order_items__discount_price') * F('order_items__quantity') + F('shipping_total')),
                    Value(0), output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )
        realized_map = {row['delivered_date']: row['realized_revenue'] for row in realized_rows}

        # ---- Expense: from Maintenance Cost via DailyProfit ----
        daily_profit_qs = DailyProfit.objects.prefetch_related('costs').all()
        if start_date:
            daily_profit_qs = daily_profit_qs.filter(date__gte=start_date)
        if end_date:
            daily_profit_qs = daily_profit_qs.filter(date__lte=end_date)

        cost_map = {}
        cost_count_map = {}
        for dp in daily_profit_qs:
            cost_map[dp.date] = dp.total_cost()
            cost_count_map[dp.date] = dp.costs.count()

        # ---- Merge into one row per date ----
        all_dates = sorted(
            set(booked_map.keys()) | set(realized_map.keys()) | set(cost_map.keys()),
            reverse=True
        )

        rows = []
        for d in all_dates:
            booked = booked_map.get(d) or 0
            realized = realized_map.get(d) or 0
            expense = cost_map.get(d) or 0
            rows.append({
                "date": d,
                "booked_revenue": booked,
                "realized_revenue": realized,
                "expense": expense,
                "expense_items": cost_count_map.get(d, 0),
                "profit": realized - expense,
            })

        per_page = parse_int(request.GET.get("per_page"), 30)
        paginator = Paginator(rows, per_page)
        page_obj = paginator.get_page(request.GET.get('page', 1))

        context = {
            "rows": page_obj,
            "paginator": paginator,
            "per_page": per_page,
            "start_date": start_date or "",
            "end_date": end_date or "",
        }

        return render(request, self.template_name, context)
# ----------------- INVOICE COLOR CONFIG -----------------


class InvoiceColorSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_settings/invoice_color_settings.html"

    def get(self, request):
        return render(request, self.template_name, {"config": InvoiceColorConfig.get_config()})

    def post(self, request):
        config = InvoiceColorConfig.get_config()
        config.header_bg = request.POST.get('header_bg')
        config.footer_bg = request.POST.get('footer_bg')
        config.header_text_color = request.POST.get('header_text_color')
        config.footer_text_color = request.POST.get('footer_text_color')
        config.highlight_color = request.POST.get('highlight_color')
        config.table_header_text_color = request.POST.get('table_header_text_color')
        config.save()
        messages.success(request, "Invoice color settings updated.")
        return redirect('invoice_color_settings')




