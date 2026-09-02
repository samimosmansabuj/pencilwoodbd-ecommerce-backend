from http import HTTPStatus
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from product.models import ProductVideo
from site_app.models import ShowcaseMedia


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