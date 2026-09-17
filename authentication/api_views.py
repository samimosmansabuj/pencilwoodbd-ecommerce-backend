import traceback
from django.db import transaction, IntegrityError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, Customer, Role
from .utils import normalize_bd_phone, phone_lookup_variants
from pencilwoodbd.extra_module import safe_error_message
from pencilwoodbd.throttles import OTPVerifyRateThrottle

class PhoneCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone = normalize_bd_phone(request.data.get("phone", ""))

        if not phone:
            return Response({"status": False, "message": "Invalid phone number"}, status=400)

        customer = Customer.objects.filter(phone__in=phone_lookup_variants(phone)).first()

        if not customer:
            return Response({"status": True, "action": "set_password", "phone": phone})

        if customer.user and customer.has_password:
            return Response({"status": True, "action": "login", "phone": phone})

        return Response({"status": True, "action": "set_password", "phone": phone})


class SetPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone = normalize_bd_phone(request.data.get("phone", ""))
        password = request.data.get("password")
        name = request.data.get("name", "").strip()

        if not phone or not password:
            return Response({"status": False, "message": "Phone and password required"}, status=400)

        if len(password) < 6:
            return Response({"status": False, "message": "Password must be at least 6 characters"}, status=400)

        try:
            with transaction.atomic():

                customer = Customer.objects.filter(phone__in=phone_lookup_variants(phone)).first()

                if customer and customer.user and customer.has_password:
                    return Response(
                        {"status": False, "message": "Account already exists. Please login."},
                        status=400
                    )

                if customer and customer.user:
                    user = customer.user
                    user.phone = phone
                    user.set_password(password)
                    user.save()
                else:
                    user = CustomUser.objects.filter(phone__in=phone_lookup_variants(phone)).first()

                    if user:
                        user.phone = phone
                        user.set_password(password)
                        user.save()
                    else:
                        user = CustomUser.objects.create_user(
                            username=phone,
                            phone=phone,
                            password=password,
                            user_type="customer"
                        )

                    if customer:
                        customer.user = user
                        customer.phone = phone
                        if name and not customer.name:
                            customer.name = name
                        customer.save()
                    else:
                        customer = Customer.objects.create(
                            user=user,
                            name=name or phone,
                            phone=phone,
                        )

                customer.has_password = True
                customer.save(update_fields=["has_password"])

                _merge_guest_cart_and_wishlist(customer, request.data)

                refresh = RefreshToken.for_user(user)

            return Response({
                "status": True,
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }, status=201)

        except IntegrityError:
            traceback.print_exc()
            customer = Customer.objects.filter(phone__in=phone_lookup_variants(phone)).first()
            if customer and customer.has_password:
                return Response(
                    {"status": False, "message": "Account already exists. Please login."},
                    status=400
                )
            return Response(
                {"status": False, "message": "Something went wrong, please try again."},
                status=409
            )

        except Exception as e:
            traceback.print_exc()
            return Response({"status": False, "message": safe_error_message(e)}, status=500)

class PhoneLoginAPIView(APIView):
    """Step 2b. Normal login when the customer already has a password set."""
    permission_classes = [AllowAny]

    def post(self, request):
        phone = normalize_bd_phone(request.data.get("phone", ""))
        password = request.data.get("password")

        if not phone:
            return Response({"status": False, "message": "Invalid phone number"}, status=400)

        try:
            user = CustomUser.objects.filter(phone__in=phone_lookup_variants(phone)).first()

            if not user or not user.check_password(password):
                return Response({"status": False, "message": "Invalid credentials"}, status=401)

            # Heal phone to normalized format on successful login
            if user.phone != phone:
                user.phone = phone
                user.save(update_fields=["phone"])

            customer = getattr(user, "customer_profile", None)
            if customer and customer.phone != phone:
                customer.phone = phone
                customer.save(update_fields=["phone"])

            refresh = RefreshToken.for_user(user)

            # Merge any guest cart/wishlist items sent along with login
            if customer:
                _merge_guest_cart_and_wishlist(customer, request.data)

            return Response({
                "status": True,
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            })

        except Exception as e:
            traceback.print_exc()
            return Response({"status": False, "message": safe_error_message(e)}, status=500)


class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyRateThrottle]

    def post(self, request):
        from site_app.models import OTPVerification

        phone = normalize_bd_phone(request.data.get("phone", ""))
        otp_code = request.data.get("otp")
        new_password = request.data.get("password")

        if not phone or not otp_code or not new_password:
            return Response(
                {"status": False, "message": "Phone, OTP and new password are required"},
                status=400
            )

        if len(new_password) < 6:
            return Response(
                {"status": False, "message": "Password must be at least 6 characters"},
                status=400
            )

        try:
            otp_obj = OTPVerification.objects.filter(phone=phone).last()
            if not otp_obj:
                return Response({"status": False, "message": "Invalid OTP"}, status=400)
            if otp_obj.is_expired():
                return Response({"status": False, "message": "OTP expired, please resend"}, status=400)
            if otp_obj.is_locked:
                return Response(
                    {"status": False, "message": "Too many attempts. Please request a new OTP."},
                    status=429,
                )
            if otp_obj.otp != otp_code:
                otp_obj.register_failed_attempt()
                if otp_obj.is_locked:
                    return Response(
                        {"status": False, "message": "Too many attempts. Please request a new OTP."},
                        status=429,
                    )
                return Response({"status": False, "message": "Invalid OTP"}, status=400)

            user = CustomUser.objects.filter(phone__in=phone_lookup_variants(phone)).first()
            if not user:
                return Response({"status": False, "message": "No account found with this number"}, status=404)

            with transaction.atomic():
                user.phone = phone
                user.set_password(new_password)
                user.save()

                customer = getattr(user, "customer_profile", None)
                if customer:
                    customer.phone = phone
                    customer.has_password = True
                    customer.save(update_fields=["phone", "has_password"])
                    _merge_guest_cart_and_wishlist(customer, request.data)

                # OTP used up — don't allow replay
                otp_obj.is_verified = True
                otp_obj.save(update_fields=["is_verified"])

                refresh = RefreshToken.for_user(user)

            return Response({
                "status": True,
                "message": "Password reset successful",
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            })

        except Exception as e:
            traceback.print_exc()
            return Response({"status": False, "message": safe_error_message(e)}, status=500)

def _merge_guest_cart_and_wishlist(customer, data):
    from product.models import AddToCart, Wishlist, Product, ProductVariant

    guest_cart = data.get("guest_cart") or []
    guest_wishlist = data.get("guest_wishlist") or []

    for row in guest_cart:
        try:
            product = Product.objects.get(id=row.get("product_id"))
        except Product.DoesNotExist:
            continue

        variant = None
        if row.get("variant_id"):
            variant = ProductVariant.objects.filter(id=row["variant_id"], product=product).first()

        existing = AddToCart.objects.filter(customer=customer, product=product, variant=variant).first()
        qty = int(row.get("quantity", 1))

        if existing:
            existing.quantity += qty
            existing.save()
        else:
            AddToCart.objects.create(customer=customer, product=product, variant=variant, quantity=qty)

    for product_id in guest_wishlist:
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            continue
        Wishlist.objects.get_or_create(customer=customer, product=product)


class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = getattr(request.user, "customer_profile", None)
        return Response({
            "status": True,
            "data": {
                "phone": request.user.phone,
                "name": customer.name if customer else "",
                "whatsapp": customer.whatsapp if customer else ""
            }
        })

    def put(self, request):
        customer = getattr(request.user, "customer_profile", None)
        if not customer:
            return Response({"status": False, "message": "Not found"}, status=404)

        customer.name = request.data.get("name", customer.name)
        customer.whatsapp = request.data.get("whatsapp", customer.whatsapp)
        customer.save()
        return Response({"status": True})


class RoleListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        roles = Role.objects.all()
        return Response({
            "status": True,
            "data": [
                {"id": r.id, "name": r.name, "can_read": r.can_read,
                 "can_add": r.can_add, "can_edit": r.can_edit, "can_delete": r.can_delete}
                for r in roles
            ]
        })


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"status": False, "message": "Refresh token required"}, status=400)
            RefreshToken(refresh_token).blacklist()
            return Response({"status": True, "message": "Logged out successfully"})
        except Exception as e:
            return Response({"status": False, "message": safe_error_message(e)}, status=400)