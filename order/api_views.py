from .serializers import OrderSerializers, OrderItemSerializer, AddressSerializers, PaymentMethodSerializers, OrderListSerializers
from rest_framework import permissions, viewsets, status, views
from rest_framework.response import Response
from .models import Order, OrderItem, PaymentMethod, Address
from authentication.models import Customer
from rest_framework.generics import CreateAPIView, ListAPIView, UpdateAPIView, RetrieveAPIView
from product.models import AddToCart
from rest_framework.exceptions import ValidationError
import json

class OrderCreateAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.data)
            print("data: ", data)
            return Response(
                {
                    "success": True,
                    "message": "Order Created"
                }, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
