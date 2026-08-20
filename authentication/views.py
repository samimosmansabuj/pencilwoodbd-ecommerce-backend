from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View

from site_app.models import LandingPageProduct
from product.models import Product


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