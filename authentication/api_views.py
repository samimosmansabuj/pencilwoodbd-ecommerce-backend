from django.contrib.auth import authenticate
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token

from .models import CustomUser, Customer, Role


# =========================
# REGISTER
# =========================
class AuthRegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            data = request.data

            email = data.get("email")
            username = data.get("username")
            password = data.get("password")

            name = data.get("name")
            phone = data.get("phone")
            whatsapp = data.get("whatsapp")

            if not email or not password:
                return Response(
                    {"status": False, "message": "Email and password required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if CustomUser.objects.filter(email=email).exists():
                return Response(
                    {"status": False, "message": "Email already exists"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            with transaction.atomic():

                user = CustomUser.objects.create_user(
                    username=username or email.split("@")[0],
                    email=email,
                    password=password,
                    user_type="customer"
                )

                Customer.objects.create(
                    user=user,
                    name=name or "",
                    phone=phone or "",
                    whatsapp=whatsapp or "",
                    email=email
                )

                token, _ = Token.objects.get_or_create(user=user)

            return Response(
                {
                    "status": True,
                    "message": "User registered successfully",
                    "token": token.key
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =========================
# LOGIN
# =========================
class AuthLoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            email = request.data.get("email")
            password = request.data.get("password")

            if not email or not password:
                return Response(
                    {"status": False, "message": "Email and password required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # IMPORTANT: email login fix
            user = authenticate(username=email, password=password)

            if not user:
                return Response(
                    {"status": False, "message": "Invalid credentials"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            token, _ = Token.objects.get_or_create(user=user)

            return Response(
                {
                    "status": True,
                    "message": "Login successful",
                    "token": token.key
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =========================
# PROFILE (GET / UPDATE)
# =========================
class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            customer = Customer.objects.filter(user=user).first()

            return Response(
                {
                    "status": True,
                    "data": {
                        "email": user.email,
                        "username": user.username,
                        "user_type": user.user_type,
                        "name": customer.name if customer else "",
                        "phone": customer.phone if customer else "",
                        "whatsapp": customer.whatsapp if customer else ""
                    }
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request):
        try:
            user = request.user
            data = request.data

            customer = Customer.objects.filter(user=user).first()

            if not customer:
                return Response(
                    {"status": False, "message": "Customer profile not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            customer.name = data.get("name", customer.name)
            customer.phone = data.get("phone", customer.phone)
            customer.whatsapp = data.get("whatsapp", customer.whatsapp)
            customer.save()

            return Response(
                {"status": True, "message": "Profile updated successfully"},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =========================
# ROLE (OPTIONAL ADMIN FUTURE USE)
# =========================
class RoleListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            roles = Role.objects.all()

            data = [
                {
                    "id": r.id,
                    "name": r.name,
                    "can_read": r.can_read,
                    "can_add": r.can_add,
                    "can_edit": r.can_edit,
                    "can_delete": r.can_delete
                }
                for r in roles
            ]

            return Response(
                {"status": True, "data": data},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )