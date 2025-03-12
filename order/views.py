from .serializers import OrderSerializers, OrderItemSerializer, AddressSerializers, PaymentMethodSerializers, OrderListSerializers
from rest_framework import permissions, viewsets, status
from rest_framework.response import Response
from .models import Order, OrderItem, PaymentMethod, Address
from authentication.models import Customer
from rest_framework.generics import CreateAPIView, ListAPIView, UpdateAPIView, RetrieveAPIView
from product.models import AddToCart
from rest_framework.exceptions import ValidationError

# ================================Order Create View Start================================
class OrderCreateViews(CreateAPIView):
    serializer_class = OrderSerializers
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_context(self):
        return {'request': self.request}

    def create(self, request, *args, **kwargs):
        customer = request.user.customer_authentication
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            carts = AddToCart.objects.filter(customer=customer)
            if not carts.exists():
                return Response({
                    'status': False,
                    'message': 'Cart is Empty!'
                }, status=status.HTTP_204_NO_CONTENT)
            address = self.get_address(serializer, customer)
            if address is None:
                return Response({
                    'status': False,
                    'message': 'Provide either a new address or select an existing one.'
                }, status=status.HTTP_204_NO_CONTENT)
            order_items = self.create_order_items(customer, carts)
            if not order_items:
                return Response({
                    'status': False,
                    'message': 'Order Items is Empty!'
                }, status=status.HTTP_204_NO_CONTENT)
            order = serializer.save(customer=customer, address=address)
            order.order_items.set(order_items)
            order.save()
            
            header = self.get_success_headers(serializer.data)
            return Response(
                {
                    'status': True,
                    'message': 'Order Create Successfully!',
                    'order': OrderListSerializers(order).data,
                }, status=status.HTTP_201_CREATED, headers=header
            )
        except ValidationError:
            error_json = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            return Response({
                'status': False,
                'error': error_json
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({
                'status': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
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
                'status': False,
                'message': 'No order items found!',
                'data': serializer.data
            },  status=status.HTTP_204_NO_CONTENT)
        else:
            return self.get_paginated_response({
                'status': True,
                'message': 'Order Items Fetched Successfully!',
                'data': serializer.data
            })
    
    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            'status': True,
            'data': response.data
        }, status=status.HTTP_200_OK)
    
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = request.data.copy()
        
        cancel = bool(data.pop('cancel', None))
        instance.name = data.pop('name')[0] if 'name' in data else instance.name
        instance.phone_number = data.pop('phone_number')[0] if 'phone_number' in data else instance.phone_number
        if cancel:
            instance.status = 'Cancel'
        instance.save()
        
        address = AddressSerializers(instance=instance.address, data=data, partial=True)
        # address.save(raise_exception=True)
        if address.is_valid():
            address.save()
        
        return Response({
            'status': True,
            'message': 'Order Information Successfully Updated!',
            'data': self.get_serializer(instance).data
        }, status=status.HTTP_200_OK)
        

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

