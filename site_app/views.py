from http import HTTPStatus
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from product.models import ProductVideo
from site_app.models import ShowcaseMedia, HomeSection, About_WhyChooseUs

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