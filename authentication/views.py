from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View

from site_app.models import LandingPageProduct
from product.models import Product

from django.core.paginator import Paginator
from django.db.models import Q
from order.models import Order
from .models import BlockedIdentity, TrackSettings, OrderTrackRecord


class LandingPageListView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        landing_pages = LandingPageProduct.objects.all().order_by("-created_at")
        return render(request, "db_landing/landing_page_list.html", {"landing_pages": landing_pages})


class LandingPageAddView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_landing/add_landing_page.html"

    def get(self, request):
        return render(request, self.template_name, {
            "products": Product.objects.order_by("name"),
            "is_update": False,
        })

    def post(self, request):
        try:
            landing = LandingPageProduct.objects.create(
                title=request.POST.get("title", "").strip(),
                description=request.POST.get("description", "").strip(),
                image=request.FILES.get("image"),
                code=request.POST.get("code", "").strip(),
                main_product_id=request.POST.get("main_product") or None,
                need_otp_verified=request.POST.get("need_otp_verified") == "on",
                is_active=request.POST.get("is_active") == "on",
                enable_pixel_tracking=request.POST.get("enable_pixel_tracking") == "on",
                facebook_pixel_id=request.POST.get("facebook_pixel_id", "").strip() or None,
                gtm_container_id=request.POST.get("gtm_container_id", "").strip() or None,
                ga4_measurement_id=request.POST.get("ga4_measurement_id", "").strip() or None,
            )
            product_ids = request.POST.getlist("product")
            if product_ids:
                landing.product.set(product_ids)

            messages.success(request, "Landing page created successfully.")
            return redirect("landing_page_list")
        except Exception as e:
            messages.error(request, f"Failed to create landing page: {e}")
            return redirect("landing_page_add")


class LandingPageEditView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_landing/add_landing_page.html"

    def get(self, request, pk):
        landing = get_object_or_404(LandingPageProduct, pk=pk)
        return render(request, self.template_name, {
            "landing": landing,
            "products": Product.objects.order_by("name"),
            "selected_product_ids": list(landing.product.values_list("id", flat=True)),
            "is_update": True,
        })

    def post(self, request, pk):
        landing = get_object_or_404(LandingPageProduct, pk=pk)
        try:
            landing.title = request.POST.get("title", "").strip()
            landing.description = request.POST.get("description", "").strip()
            landing.code = request.POST.get("code", "").strip()
            landing.main_product_id = request.POST.get("main_product") or None
            landing.need_otp_verified = request.POST.get("need_otp_verified") == "on"
            landing.is_active = request.POST.get("is_active") == "on"
            landing.enable_pixel_tracking = request.POST.get("enable_pixel_tracking") == "on"
            landing.facebook_pixel_id = request.POST.get("facebook_pixel_id", "").strip() or None
            landing.gtm_container_id = request.POST.get("gtm_container_id", "").strip() or None
            landing.ga4_measurement_id = request.POST.get("ga4_measurement_id", "").strip() or None

            new_image = request.FILES.get("image")
            if new_image:
                landing.image = new_image

            landing.save()

            product_ids = request.POST.getlist("product")
            landing.product.set(product_ids)

            messages.success(request, "Landing page updated successfully.")
            return redirect("landing_page_list")
        except Exception as e:
            messages.error(request, f"Failed to update landing page: {e}")
            return redirect("landing_page_edit", pk=pk)


class LandingPageDeleteView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        landing = get_object_or_404(LandingPageProduct, pk=pk)
        landing.delete()
        messages.success(request, "Landing page deleted.")
        return redirect("landing_page_list")
    

# --------------- IP / DEVICE BLOCKED LIST ---------------

class BlockedIdentityListView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_blocked_identity/blocked_list.html"

    def get(self, request):
        blocked_qs = BlockedIdentity.objects.filter(is_active=True).order_by("-blocked_at")

        search = request.GET.get("q", "").strip()
        if search:
            blocked_qs = blocked_qs.filter(
                Q(ip_address__icontains=search) | Q(device_hash__icontains=search)
            )

        paginator = Paginator(blocked_qs, 25)
        page_number = request.GET.get("page", 1)
        blocked_page = paginator.get_page(page_number)

        settings_obj = TrackSettings.get_solo()

        context = {
            "blocked_list": blocked_page,
            "paginator": paginator,
            "page_number": page_number,
            "current_search": search,
            "settings_obj": settings_obj,
            "mode_choices": TrackSettings.ModeChoices.choices,
            "scope_choices": TrackSettings.ScopeChoices.choices,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        settings_obj = TrackSettings.get_solo()
        mode = request.POST.get("mode")
        scope = request.POST.get("scope")
        threshold = request.POST.get("cancel_threshold")
        is_enabled = request.POST.get("is_auto_block_enabled") == "on"

        valid_modes = [c[0] for c in TrackSettings.ModeChoices.choices]
        if mode in valid_modes:
            settings_obj.mode = mode

        valid_scopes = [c[0] for c in TrackSettings.ScopeChoices.choices]
        if scope in valid_scopes:
            settings_obj.scope = scope
        try:
            threshold_int = int(threshold)
            if threshold_int > 0:
                settings_obj.cancel_threshold = threshold_int
        except (TypeError, ValueError):
            pass
        settings_obj.is_auto_block_enabled = is_enabled
        settings_obj.save()

        messages.success(request, "Track settings updated successfully.")
        return redirect("blocked_identity_list")


class UnblockIdentityView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, pk):
        blocked = get_object_or_404(BlockedIdentity, pk=pk, is_active=True)
        blocked.unblock(staff_user=request.user)
        messages.success(request, f"{blocked.ip_address} has been unblocked.")
        return redirect("blocked_identity_list")


class BlockOrderIdentityView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        track_record = OrderTrackRecord.objects.filter(order=order).order_by("-created_at").first()

        if not track_record:
            messages.error(request, "No tracking data found for this order.")
            return redirect("order_detail", id=order.id)

        already = BlockedIdentity.objects.filter(
            Q(ip_address=track_record.ip_address) | Q(device_hash=track_record.device_hash),
            is_active=True
        ).first()
        if already:
            messages.info(request, "This IP/Device is already blocked.")
        else:
            BlockedIdentity.objects.create(
                ip_address=track_record.ip_address,
                device_hash=track_record.device_hash,
                reason=BlockedIdentity.ReasonChoices.MANUAL,
                blocked_by=request.user,
                note=f"Manually blocked from Order {order.order_id}",
            )
            messages.success(request, "IP/Device blocked successfully.")
        return redirect("order_detail", id=order.id)