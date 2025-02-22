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
    
    def get_serializer_context(self):
        return {'request': self.request}
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.data)
        order_items = self.create_order_items()
        if not order_items:
            return Response(
                {'message': 'Cart is Empty!'},
                status=status.HTTP_204_NO_CONTENT
            )
        serializer['order_items'] = self.create_order_items()
        
        serializer['customer'] = self.request.user.customer_authentication
        serializer.is_valid(raise_exception=True)
        # self.perform_create(serializer)
        header = self.get_success_headers(serializer.data)
        return Response(
            {
                'message': 'Order Create Successfully!',
                'order': serializer.data,
            }, status=status.HTTP_201_CREATED, headers=header
        )
    
    def create_order_items(self):
        customer = self.request.user.customer_authentication
        order_items = []
        if AddToCart.objects.filter(customer=customer).exists():
            for cart in AddToCart.objects.filter(customer=customer):
                orderitem = OrderItem.objects.create(
                    product = cart.product,
                    customer = customer,
                    quantity = cart.quantity,
                )
                order_items.append(orderitem)
                cart.delete()
            return order_items
        else:
            return Response(
                {
                    'message': 'Cart is Empty!',
                }, status=status.HTTP_204_NO_CONTENT
            )
    
    # def perform_create(self, serializer):
    #     customer = self.request.user.customer_authentication
    #     serializer.save(customer=customer)
    
    # def get_address(self, serializer):
    #     customer = self.request.user.customer_authentication
    #     existing_addresses = serializer.get('existing_address', None)
    #     street_01 = serializer.get('street', None)
    #     upazila = serializer.get('upazila', None)
    #     district = serializer.get('district', None)
        
    #     if existing_addresses:
    #         address = existing_addresses
    #     elif street_01 and upazila and district:
    #         address = Address.objects.create(
    #             customer = customer,
    #             street_01 = street_01,
    #             upazila = upazila,
    #             district = district
    #         )
    
    
    
    # def create_order(self, customer, order_product, total_price):
    #     data = self.request.data
    #     print(data)
        
       
    # def create(self, request, *args, **kwargs):
    #     customer = self.get_customer()
    #     if not customer:
    #         return Response(
    #             {
    #                 'error': 'Customer profile not found',
    #             }, status=status.HTTP_400_BAD_REQUEST
    #         )
    #     order_items = self.create_order_item(customer)
    #     order_items_copy = order_items.copy()
    #     total_price = 0
    #     for order_items_copy in order_items_copy:
    #         total_price += order_items_copy.total_price
        
    #     order = self.create_order(customer, order_items, total_price)
    #     return Response(
    #         {
    #             'message': 'Order Create Successfully!'
    #         }
    #     )
        
        
        
        
        
        
        
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

