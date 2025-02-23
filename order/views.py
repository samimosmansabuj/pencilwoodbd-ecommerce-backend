from .serializers import OrderSerializers, OrderItemSerializer, AddressSerializers, PaymentMethodSerializers, OrderListSerializers
from rest_framework import permissions, viewsets, status
from rest_framework.response import Response
from .models import Order, OrderItem, PaymentMethod, Address
from authentication.models import Customer
from rest_framework.generics import CreateAPIView, ListAPIView, UpdateAPIView, RetrieveAPIView
from product.models import AddToCart

# ================================Order Create View Start================================
class OrderCreateViews(CreateAPIView):
    serializer_class = OrderSerializers
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_context(self):
        return {'request': self.request}
    
    def create(self, request, *args, **kwargs):
        customer = request.user.customer_authentication
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        carts = AddToCart.objects.filter(customer=customer)
        if not carts.exists():
            return Response(
                {'error': 'Cart is Empty!'},
                status=status.HTTP_204_NO_CONTENT
            )
        address = self.get_address(serializer, customer)
        if address is None:
            return Response(
                {'error': 'Provide either a new address or select an existing one.'},
                status=status.HTTP_204_NO_CONTENT
            )
        order_items = self.create_order_items(customer, carts)
        if not order_items:
            return Response(
                {'error': 'Order Items is Empty!'},
                status=status.HTTP_204_NO_CONTENT
            )
        
        order = serializer.save(customer=customer, order_items=order_items, address=address)
        order.total_cost = sum(item.total_price for item in order_items)
        order.save()
        
        header = self.get_success_headers(serializer.data)
        return Response(
            {
                'message': 'Order Create Successfully!',
                'order': OrderListSerializers(order).data,
            }, status=status.HTTP_201_CREATED, headers=header
        )
    
    def get_address(self, serializer, customer):
        existing_addresses = serializer.validated_data.pop('existing_address', None)
        street_01 = serializer.validated_data.pop('street', None)
        upazila = serializer.validated_data.pop('upazila', None)
        district = serializer.validated_data.pop('district', None)

        if existing_addresses:
            return existing_addresses
        elif street_01 and upazila and district:
            return Address.objects.create(
                customer=customer,
                street_01=street_01,
                upazila=upazila,
                district=district
            )
        else:
            return None
    
    def create_order_items(self, customer, carts):
        order_items = []
        for cart in carts:
            orderitem = OrderItem.objects.create(
                product = cart.product,
                customer = customer,
                quantity = cart.quantity,
            )
            order_items.append(orderitem)
            cart.delete()
        return order_items

# ================================Order Create View End================================


# ================================Order List, View Start================================
class OrderListViews(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderListSerializers
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user.customer_authentication)
    
    def list(self, request, *args, **kwargs):
        orders = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(orders, many=True)
        if not orders:
            return Response({
                'message': 'No order items found!',
                'data': serializer.data
            },  status=status.HTTP_204_NO_CONTENT)
        else:
            return self.get_paginated_response({
                'message': 'Order Items Fetched Successfully!',
                'data': serializer.data
            })
    
    
    # def update(self, request, *args, **kwargs):
    #     data = request.data
    #     address = data['address']
    #     instance = self.get_object()
    #     serializer = self.get_serializer(instance, data=request.data, partial=True)
        
    #     print(instance.address)
    #     print(address)
        
    #     if serializer.is_valid():
    #         serializer.save()
    #         return Response(
    #             {
    #                 'message': 'Order Updated Successfully!',
    #                 'order': request.data
    #             }, status=status.HTTP_200_OK
    #         )
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def get(self, request, *args, **kwargs):
#         if 'pk' in kwargs:
#             return self.retrieve(request, *args, **kwargs)
#         return self.list(request, *args, **kwargs)
    
#     # def put(self, request, *args, **kwargs):
#     #     return self.update(request, *args, **kwargs)
    
#     # def patch(self, request, *args, **kwargs):
#     #     return self.update(request, *args, **kwargs)
# ================================Order List, View End================================




class OrderItemViews(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
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


class PaymentMethodViews(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializers
    permission_classes = [permissions.IsAuthenticated]

class AddressViews(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializers
    permission_classes = [permissions.IsAuthenticated]

