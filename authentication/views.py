from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View

from site_app.models import LandingPageProduct
from product.models import Product

from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q
from order.models import Order
from .courier_badge import render_courier_badge
from .courier_check import describe_keep, fetch_courier_stats, purge_expired_logs, retention_label
from .courier_restricted import clear_restricted_count, restricted_new_count
from .models import CustomUser, Customer, BlockedIdentity, TrackSettings, OrderTrackRecord, CourierCheckLog, CourierCheckSettings, CourierNumberRetention
from .utils import normalize_bd_phone
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from http import HTTPStatus

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.conf import settings

from pencilwoodbd.extra_module import parse_int
from pencilwoodbd.choices import USER_TYPE, CourierCheckProviderChoices, CourierLowRatioActionChoices, CourierNoticeClearModeChoices, CourierRetentionUnitChoices

from dashbaord.views import DashboardView

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
            "landing_pages": LandingPageProduct.objects.all().order_by("-id"),
            "can_manage_otp_control": request.user.user_type in [USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN],
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
        if "blocked_message" in request.POST and request.user.user_type in [USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]:
            settings_obj.blocked_message = request.POST.get("blocked_message", "").strip()
        settings_obj.save()

        messages.success(request, "Track settings updated successfully.")
        return redirect("blocked_identity_list")


class BlockedOrderModeUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"
    ALLOWED_ROLES = (USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN)

    MODE_TEXT = {
        "otp": "OTP verification enabled",
        "deny": "OTP disabled: orders will be cancelled and the blocked message will be shown",
        "allow": "OTP disabled: orders will be accepted",
    }

    def post(self, request):
        from pencilwoodbd.choices import BlockedOrderModeChoices

        if request.user.user_type not in self.ALLOWED_ROLES:
            return JsonResponse(
                {"success": False, "message": "You do not have permission to change this setting."},
                status=403,
            )

        target = (request.POST.get("target") or "").strip()

        # ---- Blocked message ----
        if target == "message":
            text = (request.POST.get("message") or "").strip()
            if not text:
                return JsonResponse({"success": False, "message": "The message cannot be empty."}, status=400)
            settings_obj = TrackSettings.get_solo()
            settings_obj.blocked_message = text
            settings_obj.save(update_fields=["blocked_message", "updated_at"])
            return JsonResponse({"success": True, "message": "Blocked message updated."})

        # ---- OTP mode ----
        mode = (request.POST.get("mode") or "").strip()
        if mode not in BlockedOrderModeChoices.values:
            return JsonResponse({"success": False, "message": "Invalid mode."}, status=400)

        if target == "ecom":
            settings_obj = TrackSettings.get_solo()
            settings_obj.ecom_blocked_mode = mode
            settings_obj.save(update_fields=["ecom_blocked_mode", "updated_at"])
            label = "E-commerce"
        elif target.startswith("landing:"):
            try:
                landing = LandingPageProduct.objects.get(pk=int(target.split(":", 1)[1]))
            except (ValueError, LandingPageProduct.DoesNotExist):
                return JsonResponse({"success": False, "message": "Landing page not found."}, status=404)
            landing.blocked_mode = mode
            landing.save(update_fields=["blocked_mode"])
            label = landing.title or landing.code or f"Landing #{landing.pk}"
        else:
            return JsonResponse({"success": False, "message": "Invalid target."}, status=400)

        return JsonResponse({
            "success": True,
            "mode": mode,
            "message": f"{label}: {self.MODE_TEXT.get(mode, mode)}",
        })


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
        from pencilwoodbd.choices import ManualBlockScopeChoices

        order = get_object_or_404(Order, order_id=order_id)
        track_record = OrderTrackRecord.objects.filter(order=order).order_by("-created_at").first()

        phone = order.customer.phone if order.customer else None
        ip = track_record.ip_address if track_record else None
        device_hash = track_record.device_hash if track_record else None

        scope = request.POST.get("block_scope", ManualBlockScopeChoices.ALL)
        valid_scopes = [c[0] for c in ManualBlockScopeChoices.choices]
        if scope not in valid_scopes:
            scope = ManualBlockScopeChoices.ALL

        block_ip = None
        block_device = None
        block_phone = None

        if scope == ManualBlockScopeChoices.PHONE_ONLY:
            block_phone = phone
        elif scope == ManualBlockScopeChoices.IP_DEVICE_ONLY:
            block_ip = ip
            block_device = device_hash
        else:  # ALL
            block_ip = ip
            block_device = device_hash
            block_phone = phone

        if not block_ip and not block_device and not block_phone:
            messages.error(request, "No tracking data found for the selected block scope.")
            return redirect("order_detail", id=order.id)

        query = Q()
        if block_ip:
            query |= Q(ip_address=block_ip)
        if block_device:
            query |= Q(device_hash=block_device)
        if block_phone:
            query |= Q(phone=block_phone)

        already = BlockedIdentity.objects.filter(query, is_active=True).first() if query else None

        if already:
            messages.info(request, "This identity is already blocked.")
        else:
            BlockedIdentity.objects.create(
                ip_address=block_ip,
                device_hash=block_device,
                phone=block_phone,
                reason=BlockedIdentity.ReasonChoices.MANUAL,
                blocked_by=request.user,
                note=f"Manually blocked from Order {order.order_id} (scope: {scope})",
            )
            messages.success(request, "Blocked successfully.")
        return redirect("order_detail", id=order.id)

class UnblockOrderIdentityView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        track_record = OrderTrackRecord.objects.filter(order=order).order_by("-created_at").first()
        phone = order.customer.phone if order.customer else None

        ip = track_record.ip_address if track_record else None
        device_hash = track_record.device_hash if track_record else None

        query = Q()
        if ip:
            query |= Q(ip_address=ip)
        if device_hash:
            query |= Q(device_hash=device_hash)
        if phone:
            query |= Q(phone=phone)

        blocks = BlockedIdentity.objects.filter(query, is_active=True) if query else BlockedIdentity.objects.none()

        if not blocks.exists():
            messages.info(request, "No active block found for this order's identity.")
        else:
            for b in blocks:
                b.unblock(staff_user=request.user)
            messages.success(request, "Unblocked successfully.")
        return redirect("order_detail", id=order.id)

# Dashboard (staff/admin) auth & staff-management views
class UserLoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "db_auth/login.html")

    def post(self, request):
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user = authenticate(username=email, password=password)
            if user is not None and user.user_type in (
                USER_TYPE.ADMIN,
                USER_TYPE.SUPER_ADMIN,
                USER_TYPE.STAFF,
            ):
                login(request, user)
                return redirect("dashboard")
            else:
                return render(
                    request,
                    "db_auth/login.html",
                    {"error": "Invalid credentials or insufficient permissions."},
                )
        except CustomUser.DoesNotExist:
            return render(
                request, "db_auth/login.html", {"error": "User does not exist."}
            )


class AdminLogoutView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        logout(request)
        return redirect("admin_login")

# ---------------User-----------------


class UserManagementView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        tab = request.GET.get("tab", "customers")

        if tab == "staff":
            return self._staff_response(request)
        return self._customer_response(request)

    def _base_wrapper_context(self):
        orders = Order.objects.all().order_by("-created_at")
        dashboard_view = DashboardView()
        return {
            "status_amounts": dashboard_view.get_status_amounts(orders),
            "today_order_count": dashboard_view.get_today_order_count(orders),
            "new_orders_count": dashboard_view.new_orders_count(orders),
            "total_orders": orders.count(),
            "new_order_request_count": dashboard_view.new_order_request_count(),
            "urgent_count": dashboard_view.get_urgent_count(orders),   
            
        }

    def _customer_response(self, request):
        search = request.GET.get("q", "").strip()

        customers = Customer.objects.select_related("user").order_by("-created_at")

        if search:
            customers = customers.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(second_phone__icontains=search)
                | Q(email__icontains=search)
                | Q(company__icontains=search)
            ).distinct()

        per_page = parse_int(request.GET.get("per_page"), 10)
        paginator = Paginator(customers, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "active_tab": "customers",
            "customers": page_obj,
            "paginator": paginator,
            "current_search": search,
            "current_per_page": str(per_page),
        }

        if request.htmx:
            return render(request, "db_users/partial/partial_customer_list.html", context)

        context.update(self._base_wrapper_context())
        return render(request, "db_users/user_management.html", context)

    def _staff_response(self, request):
        search = request.GET.get("q", "").strip()
        role = request.GET.get("role", "").strip()

        staff_users = CustomUser.objects.exclude(user_type=USER_TYPE.CUSTOMER).order_by("-date_joined")

        if search:
            staff_users = staff_users.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            ).distinct()

        valid_roles = [c[0] for c in USER_TYPE.choices]
        if role in valid_roles and role != USER_TYPE.CUSTOMER:
            staff_users = staff_users.filter(user_type=role)

        per_page = parse_int(request.GET.get("per_page"), 10)
        paginator = Paginator(staff_users, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        role_choices = [c for c in USER_TYPE.choices if c[0] != USER_TYPE.CUSTOMER]

        context = {
            "active_tab": "staff",
            "staff_users": page_obj,
            "paginator": paginator,
            "current_search": search,
            "current_role": role,
            "current_per_page": str(per_page),
            "role_choices": role_choices,
        }

        if request.htmx:
            return render(request, "db_users/partial/partial_staff_list.html", context)

        context.update(self._base_wrapper_context())
        return render(request, "db_users/user_management.html", context)


class StaffCreateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def _can_manage_staff(self, request):
        return request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

    def post(self, request):
        if not self._can_manage_staff(request):
            messages.error(request, "You don't have permission to create staff/admin users.")
            return redirect("user_management")

        data = request.POST
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")
        role = data.get("user_type", "").strip()

        redirect_url = f"{reverse_lazy('user_management')}?tab=staff"
        assignable_roles = [USER_TYPE.STAFF, USER_TYPE.ADMIN]

        if not username or not email or not password:
            messages.error(request, "Username, email and password are required.")
            return redirect(redirect_url)

        if role not in assignable_roles:
            messages.error(request, "Invalid role selected.")
            return redirect(redirect_url)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect(redirect_url)

        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered.")
            return redirect(redirect_url)

        try:
            with transaction.atomic():
                user = CustomUser.objects.create(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    user_type=role,
                    password=make_password(password),
                    is_active=True,
                    is_staff=True,  # allows Django-admin login if ever needed
                )
            messages.success(request, f"{user.get_user_type_display()} account for '{username}' created successfully.")
        except Exception as e:
            messages.error(request, f"Failed to create user: {e}")

        return redirect(redirect_url)


class StaffUpdateView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def _can_manage_staff(self, request):
        return request.user.user_type in [USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN]

    def get(self, request, pk):
        # Only admins can edit others; a user can edit only themselves otherwise
        target = get_object_or_404(CustomUser, pk=pk)
        if not self._can_manage_staff(request) and request.user.pk != target.pk:
            return JsonResponse({"status": False, "message": "Permission denied"}, status=HTTPStatus.FORBIDDEN)

        return JsonResponse({
            "status": True,
            "user": {
                "id": target.id,
                "username": target.username,
                "email": target.email,
                "first_name": target.first_name,
                "last_name": target.last_name,
                "user_type": target.user_type,
                "is_active": target.is_active,
            }
        })

    def post(self, request, pk):
        target = get_object_or_404(CustomUser, pk=pk)
        is_self = request.user.pk == target.pk
        is_manager = self._can_manage_staff(request)

        if not is_manager and not is_self:
            messages.error(request, "You don't have permission to edit this user.")
            return redirect("user_management")

        redirect_url = f"{reverse_lazy('user_management')}?tab=staff"
        data = request.POST

        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")
        role = data.get("user_type", "").strip()

        if not username or not email:
            messages.error(request, "Username and email are required.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(username=username).exclude(pk=target.pk).exists():
            messages.error(request, "This username is already taken.")
            return redirect(redirect_url)

        if CustomUser.objects.filter(email=email).exclude(pk=target.pk).exists():
            messages.error(request, "This email is already registered.")
            return redirect(redirect_url)

        # Role change: only a manager can change roles, and never to/from SUPER_ADMIN via this form
        if is_manager:
            assignable_roles = [USER_TYPE.STAFF, USER_TYPE.ADMIN]
            if role and target.user_type != USER_TYPE.SUPER_ADMIN:
                if role not in assignable_roles:
                    messages.error(request, "Invalid role selected.")
                    return redirect(redirect_url)
                target.user_type = role
            # is_active toggle, manager only
            target.is_active = data.get("is_active") == "on"

        # Password change (optional on edit)
        if password or confirm_password:
            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return redirect(redirect_url)
            if len(password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return redirect(redirect_url)
            target.password = make_password(password)

        target.username = username
        target.email = email
        target.first_name = first_name
        target.last_name = last_name

        try:
            target.save()
            messages.success(request, f"User '{target.username}' updated successfully.")
        except Exception as e:
            messages.error(request, f"Failed to update user: {e}")

        return redirect(redirect_url)


COURIER_ROLES = (USER_TYPE.STAFF, USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN)


class CourierCheckSettingsView(LoginRequiredMixin, View):
    login_url = "admin_login"
    template_name = "db_courier_check/courier_check.html"

    def get(self, request):
        cfg = CourierCheckSettings.get_solo()

        latest_ids = CourierCheckLog.objects.values("phone").annotate(last_id=Max("id")).values("last_id")
        logs = CourierCheckLog.objects.filter(id__in=latest_ids)
        g = request.GET
        q = g.get("q", "").strip()
        if q:
            logs = logs.filter(phone__icontains=q)

        def _date(key):
            try:
                return datetime.strptime(g.get(key, ""), "%Y-%m-%d").date()
            except ValueError:
                return None

        def _percent(key):
            try:
                v = Decimal(g.get(key, ""))
            except (InvalidOperation, TypeError):
                return None
            return v if Decimal("0") <= v <= Decimal("100") else None

        start_date, end_date = _date("start_date"), _date("end_date")
        min_ratio, max_ratio = _percent("min_ratio"), _percent("max_ratio")
        source = g.get("source", "").strip()
        result_filter = g.get("result", "").strip()
        if start_date:
            logs = logs.filter(created_at__date__gte=start_date)
        if end_date:
            logs = logs.filter(created_at__date__lte=end_date)
        if min_ratio is not None:
            logs = logs.filter(success_ratio__gte=min_ratio)
        if max_ratio is not None:
            logs = logs.filter(success_ratio__lte=max_ratio)
        if source:
            logs = logs.filter(source=source)
        if result_filter == "ok":
            logs = logs.filter(is_error=False)
        elif result_filter == "failed":
            logs = logs.filter(is_error=True)

        try:
            per_page = int(g.get("per_page", 20))
        except ValueError:
            per_page = 20
        if per_page not in (10, 20, 50, 100):
            per_page = 20
        page = Paginator(logs.order_by("-created_at"), per_page).get_page(g.get("page", 1))

        qs = urlencode({k: v for k, v in (
            ("q", q), ("start_date", g.get("start_date", "") if start_date else ""), ("end_date", g.get("end_date", "") if end_date else ""),
            ("min_ratio", g.get("min_ratio", "") if min_ratio is not None else ""), ("max_ratio", g.get("max_ratio", "") if max_ratio is not None else ""),
            ("source", source), ("result", result_filter), ("per_page", per_page),
        ) if v != ""})

        phones = [log.phone for log in page]
        counts = dict(CourierCheckLog.objects.filter(phone__in=phones).values_list("phone").annotate(n=Count("id")))
        rules = {r.phone: r for r in CourierNumberRetention.objects.filter(phone__in=phones)}
        for log in page:
            log.check_count = counts.get(log.phone, 0)
            log.keep = describe_keep(cfg, rules.get(log.phone))

        recent_only = g.get("part") == "recent"
        stats = {}
        if not recent_only:
            stats = CourierCheckLog.objects.aggregate(total=Count("id"), oldest=Min("created_at"))
            stats["numbers"] = CourierCheckLog.objects.values("phone").distinct().count()
            stats["expired"] = purge_expired_logs(cfg, dry_run=True)

        context = {
            "per_page": per_page,
            "per_page_choices": (10, 20, 50, 100),
            "qs": qs,
            "f_start_date": g.get("start_date", "") if start_date else "",
            "f_end_date": g.get("end_date", "") if end_date else "",
            "f_min_ratio": g.get("min_ratio", "") if min_ratio is not None else "",
            "f_max_ratio": g.get("max_ratio", "") if max_ratio is not None else "",
            "f_source": source,
            "f_result": result_filter,
            "source_choices": list(CourierCheckLog.objects.exclude(source="").values_list("source", flat=True).distinct().order_by("source")),
            "filters_active": bool(q or start_date or end_date or min_ratio is not None or max_ratio is not None or source or result_filter),
            "cfg": cfg,
            "action_choices": CourierLowRatioActionChoices.choices,
            "provider_choices": CourierCheckProviderChoices.choices,
            "unit_choices": CourierRetentionUnitChoices.choices,
            "clear_mode_choices": CourierNoticeClearModeChoices.choices,
            "restricted_new": restricted_new_count(cfg),
            "logs": page,
            "stats": stats,
            "keep_text": retention_label(cfg.retention_forever, cfg.retention_value, cfg.retention_unit),
            "current_search": q,
            "can_edit": request.user.user_type in COURIER_ROLES,
        }
        if recent_only:
            return render(request, "db_courier_check/partial/partial_courier_recent_checks.html", context)
        if request.htmx:
            return render(request, "db_courier_check/partial/partial_courier_check_settings.html", context)
        return render(request, self.template_name, context)

    def post(self, request):
        if request.user.user_type not in COURIER_ROLES:
            messages.error(request, "You do not have permission to change these settings.")
            return redirect("courier_check_settings")

        cfg = CourierCheckSettings.get_solo()
        p = request.POST

        cfg.is_enabled = p.get("is_enabled") == "on"
        cfg.apply_on_ecom = p.get("apply_on_ecom") == "on"
        cfg.apply_on_landing = p.get("apply_on_landing") == "on"
        cfg.fail_open = p.get("fail_open") == "on"
        cfg.show_badges = p.get("show_badges") == "on"
        cfg.auto_check_new_numbers = p.get("auto_check_new_numbers") == "on"

        if p.get("provider") in dict(CourierCheckProviderChoices.choices):
            cfg.provider = p["provider"]
        if p.get("low_ratio_action") in dict(CourierLowRatioActionChoices.choices):
            cfg.low_ratio_action = p["low_ratio_action"]

        base = (p.get("api_base_url") or "").strip()
        if base.startswith(("http://", "https://")):
            cfg.api_base_url = base.rstrip("/")
        endpoint = (p.get("api_endpoint") or "").strip()
        if endpoint:
            cfg.api_endpoint = "/" + endpoint.lstrip("/")

        new_key = (p.get("api_key") or "").strip()
        if new_key:
            cfg.api_key = new_key
        elif p.get("clear_api_key") == "on":
            cfg.api_key = ""

        try:
            ratio = Decimal(p.get("min_success_ratio", "")).quantize(Decimal("0.01"))
            if Decimal("0") <= ratio <= Decimal("100"):
                cfg.min_success_ratio = ratio
            else:
                messages.warning(request, "Success ratio must be between 0 and 100. Old value kept.")
        except (InvalidOperation, TypeError):
            pass

        try:
            margin = Decimal(p.get("warn_margin", "")).quantize(Decimal("0.01"))
            if Decimal("0") <= margin <= Decimal("100"):
                cfg.warn_margin = margin
        except (InvalidOperation, TypeError):
            pass

        for field, lo, hi in (("min_parcels_to_evaluate", 1, 1000), ("cache_hours", 0, 720), ("timeout_seconds", 1, 30), ("api_retries", 0, 3), ("auto_check_hourly_limit", 0, 100000)):
            try:
                val = int(p.get(field, ""))
                if lo <= val <= hi:
                    setattr(cfg, field, val)
            except (TypeError, ValueError):
                pass

        cfg.whatsapp_number = (p.get("whatsapp_number") or "").strip()[:20]
        cfg.whatsapp_prefill_text = (p.get("whatsapp_prefill_text") or "").strip()[:255]
        cfg.ignored_couriers = (p.get("ignored_couriers") or "").strip()[:255]
        if (p.get("otp_message") or "").strip():
            cfg.otp_message = p["otp_message"].strip()
        if (p.get("whatsapp_message") or "").strip():
            cfg.whatsapp_message = p["whatsapp_message"].strip()

        cfg.hard_block_enabled = p.get("hard_block_enabled") == "on"
        try:
            hard = Decimal(p.get("hard_block_ratio", "")).quantize(Decimal("0.01"))
            if Decimal("0") <= hard <= Decimal("100"):
                cfg.hard_block_ratio = hard
        except (InvalidOperation, TypeError):
            pass
        if (p.get("hard_block_message") or "").strip():
            cfg.hard_block_message = p["hard_block_message"].strip()
        cfg.hard_block_contact = (p.get("hard_block_contact") or "").strip()[:60]
        if p.get("restricted_clear_mode") in dict(CourierNoticeClearModeChoices.choices):
            cfg.restricted_clear_mode = p["restricted_clear_mode"]
        cfg.restricted_expire_forever = p.get("restricted_expire_mode", "limited") == "forever"
        if p.get("restricted_expire_unit") in dict(CourierRetentionUnitChoices.choices):
            cfg.restricted_expire_unit = p["restricted_expire_unit"]
        try:
            expire_value = int(p.get("restricted_expire_value", ""))
            if 1 <= expire_value <= 1000:
                cfg.restricted_expire_value = expire_value
        except (TypeError, ValueError):
            pass

        cfg.retention_forever = p.get("retention_mode", "forever") != "limited"
        if p.get("retention_unit") in dict(CourierRetentionUnitChoices.choices):
            cfg.retention_unit = p["retention_unit"]
        try:
            keep_value = int(p.get("retention_value", ""))
            if 1 <= keep_value <= 1000:
                cfg.retention_value = keep_value
        except (TypeError, ValueError):
            pass

        cfg.save()
        messages.success(request, "Courier check settings saved.")
        return redirect("courier_check_settings")


class CourierBadgeCheckView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        if request.user.user_type not in COURIER_ROLES:
            return JsonResponse({"success": False, "message": "Permission denied."}, status=403)

        phone = normalize_bd_phone(request.POST.get("phone", ""))
        if not phone:
            return JsonResponse({"success": False, "message": "Invalid phone number."}, status=400)

        cfg = CourierCheckSettings.get_solo()
        if not (cfg.api_key or "").strip():
            return JsonResponse({"success": False, "message": "Save the API key in Courier Check settings first."}, status=400)

        result = fetch_courier_stats(phone, cfg=cfg, source="dashboard")
        if not result.ok:
            return JsonResponse({"success": False, "message": result.error or "Courier API error."}, status=502)

        return JsonResponse({"success": True, "html": render_courier_badge(phone, cfg=cfg)})


def render_courier_history(request, phone_raw, saved_message=""):
    phone = normalize_bd_phone(phone_raw)
    if not phone:
        return HttpResponse("Invalid phone number.", status=400)

    cfg = CourierCheckSettings.get_solo()
    limit = 200
    all_logs = CourierCheckLog.objects.filter(phone=phone).order_by("-created_at")
    rule = CourierNumberRetention.objects.filter(phone=phone).first()
    if rule is None:
        form_mode = "default"
    else:
        form_mode = "forever" if rule.keep_forever else "limited"
    return render(request, "db_courier_check/partial/partial_courier_check_history.html", {
        "cfg": cfg,
        "phone": phone,
        "logs": all_logs[:limit],
        "total": all_logs.count(),
        "limit": limit,
        "rule": rule,
        "form_mode": form_mode,
        "form_value": rule.value if rule else 30,
        "form_unit": rule.unit if rule else "day",
        "keep": describe_keep(cfg, rule),
        "system_keep": retention_label(cfg.retention_forever, cfg.retention_value, cfg.retention_unit),
        "unit_choices": CourierRetentionUnitChoices.choices,
        "saved_message": saved_message,
        "can_edit": request.user.user_type in COURIER_ROLES,
    })


class CourierCheckHistoryView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def get(self, request):
        return render_courier_history(request, request.GET.get("phone", ""))


class CourierNumberRetentionView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        if request.user.user_type not in COURIER_ROLES:
            return HttpResponse("You do not have permission to change this.", status=403)

        phone = normalize_bd_phone(request.POST.get("phone", ""))
        if not phone:
            return HttpResponse("Invalid phone number.", status=400)

        mode = request.POST.get("mode", "default")
        if mode == "forever":
            CourierNumberRetention.objects.update_or_create(phone=phone, defaults={"keep_forever": True})
            message = "Saved: this number's history is kept forever."
        elif mode == "limited":
            unit = request.POST.get("unit")
            try:
                value = int(request.POST.get("value", ""))
            except (TypeError, ValueError):
                value = 0
            if unit not in dict(CourierRetentionUnitChoices.choices) or not 1 <= value <= 1000:
                return render_courier_history(request, phone, "Enter a number between 1 and 1000 and pick a unit. Nothing was changed.")
            CourierNumberRetention.objects.update_or_create(
                phone=phone, defaults={"keep_forever": False, "value": value, "unit": unit}
            )
            message = f"Saved: older checks of this number are deleted after {retention_label(False, value, unit)}."
        else:
            CourierNumberRetention.objects.filter(phone=phone).delete()
            message = "Saved: this number now follows the system setting."
        return render_courier_history(request, phone, message)


class CourierCheckCleanupView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        if request.user.user_type not in COURIER_ROLES:
            messages.error(request, "You do not have permission to do this.")
            return redirect("courier_check_settings")
        deleted = purge_expired_logs()
        messages.success(request, f"Deleted {deleted} expired courier check record(s).")
        return redirect("courier_check_settings")


class CourierRestrictedClearView(LoginRequiredMixin, View):
    login_url = "admin_login"

    def post(self, request):
        if request.user.user_type not in COURIER_ROLES:
            return JsonResponse({"success": False, "message": "Permission denied."}, status=403)
        clear_restricted_count()
        return JsonResponse({"success": True})
