from django.shortcuts import render
from .serializers import OrderSerializers, OrderItemSerializers, AddressSerializers, PaymentMethodSerializers
from rest_framework import permissions, viewsets, status
from rest_framework.response import Response
from .models import Order, OrderItem, PaymentMethod, Address
from authentication.models import Customer
from rest_framework.generics import CreateAPIView
from product.models import AddToCart


class OrderCreateViews(CreateAPIView):
    serializer_class = OrderSerializers
    permission_classes = [permissions.IsAuthenticated]
    
    def get_customer(self):
        try:
            return self.request.user.customer_authentication
        except Customer.DoesNotExist:
            return None
    
    def create(self, request, *args, **kwargs):
        customer = self.get_customer()
        if not customer:
            return Response(
                {
                    'error': 'Customer profile not found',
                }, status=status.HTTP_400_BAD_REQUEST
            )
        
        customer_cart = AddToCart.objects.filter(customer=customer)
        for cart in customer_cart:
            OrderItem.objects.create(
                product = cart.product,
                customer = customer,
                quantity = cart.quantity,
                price = cart.product.discount_price
            )
        
        
        # return super().create(request, *args, **kwargs)

class OrderItemViews(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializers
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request, *args, **kwargs):
        order_item = self.paginate_queryset(self.get_queryset())
        if request.user.is_authenticated:
            if order_item is not None:
                serializer = self.get_serializer(order_item, many=True)
                return self.get_paginated_response({
                    'message': 'Order Items Fetched Successfully!',
                    'data': serializer.data
                })
            serializer = self.get_serializer(order_item, many=True)
            return Response({
                'message': 'No order items found!',
                'data': serializer.data
            })
        else:
            return Response(
                {
                    'error': 'Authentication Failed!',
                }, status=status.HTTP_401_UNAUTHORIZED
            )
    
    def get_queryset(self):
        try:
            customer = self.request.user.customer_authentication
            return OrderItem.objects.filter(customer=customer)
        except Customer.DoesNotExist:
            return OrderItem.objects.none
    
    


class OrderViews(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializers
    permission_classes = [permissions.IsAuthenticated]

class PaymentMethodViews(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializers
    permission_classes = [permissions.IsAuthenticated]

class AddressViews(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializers
    permission_classes = [permissions.IsAuthenticated]

