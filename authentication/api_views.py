from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token

from .models import CustomUser, Customer, Role


class AuthRegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            data = request.data

            email = data.get("email")
            username = data.get("username")
            password = data.get("password")

            name = data.get("name", "")
            phone = data.get("phone", "")
            whatsapp = data.get("whatsapp", "")

            if not email or not password:
                return Response(
                    {"status": False, "message": "Email and password required"},
                    status=400
                )

            if CustomUser.objects.filter(email=email).exists():
                return Response(
                    {"status": False, "message": "Email already exists"},
                    status=400
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
                    name=name,
                    phone=phone,
                    whatsapp=whatsapp,
                    email=email
                )

                token, _ = Token.objects.get_or_create(user=user)

            return Response({
                "status": True,
                "token": token.key
            }, status=201)

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)


class AuthLoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            email = request.data.get("email")
            password = request.data.get("password")

            user = CustomUser.objects.filter(email=email).first()

            if not user or not user.check_password(password):
                return Response(
                    {"status": False, "message": "Invalid credentials"},
                    status=401
                )

            token, _ = Token.objects.get_or_create(user=user)

            return Response({
                "status": True,
                "token": token.key
            })

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)


class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        customer = getattr(user, "customer_profile", None)

        return Response({
            "status": True,
            "data": {
                "email": user.email,
                "username": user.username,
                "name": customer.name if customer else "",
                "phone": customer.phone if customer else "",
                "whatsapp": customer.whatsapp if customer else ""
            }
        })

    def put(self, request):
        customer = getattr(request.user, "customer_profile", None)

        if not customer:
            return Response({"status": False, "message": "Not found"}, status=404)

        customer.name = request.data.get("name", customer.name)
        customer.phone = request.data.get("phone", customer.phone)
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
                {
                    "id": r.id,
                    "name": r.name,
                    "can_read": r.can_read,
                    "can_add": r.can_add,
                    "can_edit": r.can_edit,
                    "can_delete": r.can_delete
                } for r in roles
            ]
        })