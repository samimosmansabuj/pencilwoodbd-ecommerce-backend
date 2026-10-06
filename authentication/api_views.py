import traceback
import uuid
from django.conf import settings
from django.db import transaction, IntegrityError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, Customer, Role
from .utils import normalize_bd_phone, phone_lookup_variants
from pencilwoodbd.extra_module import safe_error_message
from pencilwoodbd.throttles import OTPVerifyRateThrottle, GoogleAuthRateThrottle

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

# GOOGLE LOGIN
def _unique_username(base):
    base = (base or "user")[:140]
    username = base
    while CustomUser.objects.filter(username=username).exists():
        username = f"{base}-{uuid.uuid4().hex[:6]}"
    return username


class GoogleLoginAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [GoogleAuthRateThrottle]

    def post(self, request):
        credential = (request.data.get("credential") or "").strip()
        if not credential:
            return Response({"status": False, "message": "Google credential required"}, status=400)

        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        if not client_id:
            return Response({"status": False, "message": "Google login is not configured"}, status=503)

        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests

            info = google_id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                client_id,
                clock_skew_in_seconds=10,
            )
        except ValueError:
            return Response({"status": False, "message": "Invalid or expired Google login. Please try again."}, status=401)
        except Exception:
            traceback.print_exc()
            return Response({"status": False, "message": "Could not verify Google login. Please try again."}, status=503)

        sub = str(info.get("sub") or "")
        email = (info.get("email") or "").strip().lower()
        if not sub or not email:
            return Response({"status": False, "message": "Google account has no email"}, status=400)
        if not info.get("email_verified"):
            return Response({"status": False, "message": "Your Google email is not verified"}, status=400)

        full_name = (info.get("name") or "").strip() or email.split("@")[0]

        try:
            with transaction.atomic():
                created = False
                user = CustomUser.objects.filter(google_id=sub).first()

                if not user:
                    user = CustomUser.objects.filter(email__iexact=email).first()
                    if user:
                        if user.user_type != "customer":
                            return Response(
                                {"status": False, "message": "This account cannot log in with Google."},
                                status=403,
                            )
                        user.google_id = sub
                        user.save(update_fields=["google_id"])
                    else:
                        user = CustomUser(
                            username=_unique_username(email),
                            email=email,
                            first_name=(info.get("given_name") or "")[:150],
                            last_name=(info.get("family_name") or "")[:150],
                            user_type="customer",
                            google_id=sub,
                        )
                        user.set_unusable_password()
                        user.save()
                        created = True

                if not user.is_active:
                    return Response({"status": False, "message": "This account is disabled."}, status=403)
                if user.user_type != "customer":
                    return Response(
                        {"status": False, "message": "This account cannot log in with Google."},
                        status=403,
                    )

                customer = getattr(user, "customer_profile", None)
                if not customer:
                    customer = Customer.objects.create(
                        user=user,
                        name=full_name[:50],
                        email=email,
                    )
                elif not customer.email:
                    customer.email = email
                    customer.save(update_fields=["email"])

                refresh = RefreshToken.for_user(user)

            return Response({
                "status": True,
                "is_new_user": created,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }, status=201 if created else 200)

        except IntegrityError:
            traceback.print_exc()
            return Response(
                {"status": False, "message": "Something went wrong, please try again."},
                status=409,
            )
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
                "whatsapp": customer.whatsapp if customer else "",
                "email": request.user.email or (customer.email if customer else "") or ""
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