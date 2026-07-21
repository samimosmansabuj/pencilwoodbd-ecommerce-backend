from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, Customer, Role
from .utils import normalize_bd_phone  


class PhoneCheckAPIView(APIView):
    """
    Step 1 of login. Given a phone number, tells the frontend
    whether to show 'set password' or 'enter password'.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = normalize_bd_phone(request.data.get("phone", ""))

        if not phone:
            return Response({"status": False, "message": "Invalid phone number"}, status=400)
        
        customer = Customer.objects.filter(phone=phone).first()

        if not customer:
            return Response({"status": True, "action": "set_password", "phone": phone})

        if customer.user and customer.has_password:
            return Response({"status": True, "action": "login", "phone": phone})

        return Response({"status": True, "action": "set_password", "phone": phone})


class SetPasswordAPIView(APIView):
    """
    Step 2a. Creates (or attaches) a CustomUser to the Customer for this phone,
    and sets their password. Used both for:
      - a guest who ordered before and is logging in for the first time
      - a brand-new user who never ordered, creating an account directly
    """
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
                customer = Customer.objects.filter(phone=phone).first()

                if customer and customer.user and customer.has_password:
                    return Response(
                        {"status": False, "message": "Account already exists. Please login."},
                        status=400
                    )

                if customer and customer.user:
                    # Customer + user shell already exists (edge case), just set password
                    user = customer.user
                    user.set_password(password)
                    user.save()
                else:
                    # Create the CustomUser
                    user = CustomUser.objects.create_user(
                        username=phone,
                        phone=phone,
                        password=password,
                        user_type="customer"
                    )

                    if customer:
                        # Guest customer from a prior order — attach user to it
                        customer.user = user
                        if name and not customer.name:
                            customer.name = name
                        customer.save()
                    else:
                        # Brand new customer, never ordered before
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

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)


class PhoneLoginAPIView(APIView):
    """Step 2b. Normal login when the customer already has a password set."""
    permission_classes = [AllowAny]

    def post(self, request):
        phone = normalize_bd_phone(request.data.get("phone", ""))
        password = request.data.get("password")

        user = CustomUser.objects.filter(phone=phone).first()

        if not user or not user.check_password(password):
            return Response({"status": False, "message": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)

        # Merge any guest cart/wishlist items sent along with login
        customer = getattr(user, "customer_profile", None)
        if customer:
            _merge_guest_cart_and_wishlist(customer, request.data)

        return Response({
            "status": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        })


def _merge_guest_cart_and_wishlist(customer, data):
    """
    Frontend sends guest cart/wishlist as JSON in the login/set-password payload:
      guest_cart: [{product_id, variant_id, quantity}, ...]
      guest_wishlist: [product_id, ...]
    We upsert these into the customer's real cart/wishlist.
    """
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
            return Response({"status": False, "message": str(e)}, status=400)