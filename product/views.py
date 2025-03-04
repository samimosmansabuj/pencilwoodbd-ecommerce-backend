from django.shortcuts import render
from .serializers import CategorySerializer, ProductSerializer, AddToCartSerializer, FreeAddToCartSerializer
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import Category, Product, AddToCart, FreeAddToCart
from authentication.models import Customer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser


class AdminCreationPermision(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.user_type in {'Admin', 'Super Admin', 'Staff'}

class CategoryViewset(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AdminCreationPermision]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title', 'details', 'slug']
    parser_classes = [MultiPartParser]
    
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response(
            {
                'message': 'Category Successfully Created!',
                'category': response.data,
            }, status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {
                'message': 'Category Successfully Updated!',
                'category': response.data,
            }, status=status.HTTP_200_OK
        )
    
    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        category.delete()
        return Response(
            {
                'message': 'Category Successfully Deleted!'
            }, status=status.HTTP_204_NO_CONTENT
        )


class ProductViewset(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AdminCreationPermision]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title', 'short_description', 'slug', 'details']
    parser_classes = [MultiPartParser]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(
            {
                'message': 'Product Successfully Created',
                # 'product': ProductSerializer(product).data,
            }, status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {
                'message': 'Product Successfully Updated!',
                'product': response.data,
            }, status=status.HTTP_200_OK,
        )
    
    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        product.delete()
        return Response(
            {
                'message': 'Product Successfully Deleted!'
            }, status=status.HTTP_204_NO_CONTENT
        )
 





class AddToCartViewset(viewsets.ModelViewSet):
    queryset = AddToCart.objects.all()
    serializer_class = AddToCartSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_customer(self):
        try:
            return self.request.user.customer_authentication
        except Customer.DoesNotExist:
            return None
    
    def get_cart(self, request):
        if request.user.is_authenticated:
            try:
                customer = request.user.customer_authentication
                return AddToCart.objects.filter(customer=customer)
            except Customer.DoesNotExist:
                return None
        else:
            session_cart = request.session.get("cart", {})
            print(request.session.session_key)
            return session_cart
    
    
    def list(self, request, *args, **kwargs):
        cart = self.get_cart(request)
        if request.user.is_authenticated:
            return Response(
                AddToCartSerializer(cart, many=True).data, status=status.HTTP_200_OK
            )
        else:
            if len(cart) is 0:
                return Response(
                    {
                        'message': 'Cart is Empty!',
                    }, status=status.HTTP_204_NO_CONTENT
                )
            return Response(cart, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            customer = self.get_customer()
            if not customer:
                return Response(
                    {
                        'error': 'Customer profile not found!',
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            cart = self.get_object()
            cart.delete()
            return Response(
                {
                    'message': 'Cart Successfully Deleted!',
                    'cart': AddToCartSerializer(AddToCart.objects.filter(customer=customer), many=True).data,
                }, status=status.HTTP_204_NO_CONTENT
            )
        else:
            product_id = str(kwargs.get('pk'))
            session_cart = request.session.get('cart', {})
            if product_id in session_cart:
                del session_cart[product_id]
            else:
                return Response(
                    {
                        'error': 'Cart not found!',
                        'cart': session_cart
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            
            request.session['cart'] = session_cart
            request.session.modified = True
            return Response(
                {
                    'message': 'Product removed from cart!',
                    'cart': session_cart
                }, status=status.HTTP_200_OK
            )
    
    def create(self, request, *args, **kwargs):
        print(request.session.session_key)
        print("Before Adding:", request.session.get("cart", {}))  # Debugging line
        product_id = request.data.get('product')
        if product_id is None:
            return Response(
                {
                    'message': 'Product Fields is Required!'
                }, status=status.HTTP_204_NO_CONTENT
            )
        product = Product.objects.get(id=product_id)
        
        if request.user.is_authenticated:
            customer = self.get_customer()
            if not customer:
                return Response(
                    {
                        'error': 'Customer profile not found',
                    }, status=status.HTTP_400_BAD_REQUEST
                )
        
            existing_cart_item = AddToCart.objects.filter(
                customer=customer, product=product
            ).first()
            
            if existing_cart_item:
                existing_cart_item.quantity += 1
                existing_cart_item.save()
            else:
                AddToCart.objects.create(customer=customer, product=product, quantity=1)
            return Response(
                {
                    'message': 'Product added to cart!',
                    'cart': AddToCartSerializer(AddToCart.objects.filter(customer=customer), many=True).data,
                }, status=status.HTTP_201_CREATED,
            )
        else:
            sessoin_cart = request.session.get("cart", {})
            if str(product_id) in sessoin_cart:
                sessoin_cart[str(product_id)]["quantity"] += 1
            else:
                sessoin_cart[str(product_id)] = {'quantity': 1, 'product_name': product.name, 'current_price': float(product.current_price), 'discount_price': float(product.discount_price)}
            request.session['cart'] = sessoin_cart
            request.session.modified = True
            print("After Adding:", request.session.get("cart", {}))  # Debugging line
            return Response(
                {
                    'message': 'Product added to cart!',
                    'cart': sessoin_cart
                }, status=status.HTTP_201_CREATED
            )
    
    def update(self, request, *args, **kwargs):
        action = request.data.get('action')
        
        if request.user.is_authenticated:
            customer = self.get_customer()
            if not customer:
                return Response(
                    {
                        'error': 'Customer profile not found',
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            customer_cart = AddToCart.objects.filter(customer=customer)
            instance = self.get_object()
            if action == 'increase':
                instance.quantity += 1
            elif action == 'decrease':
                if instance.quantity > 1:
                    instance.quantity -= 1
                else:
                    instance.delete()
                    return Response(
                        {
                            'message': 'Product remove from cart!',
                            'cart': AddToCartSerializer(customer_cart, many=True).data,
                        }, status=status.HTTP_200_OK
                    )
            else:
                return Response(
                    {
                        'error': 'Invalid Action! use "increase" or "decrease".',
                        'cart': AddToCartSerializer(customer_cart, many=True).data,
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            
            instance.save()
            return Response(
                {
                    'message': 'Cart successfully updated!',
                    'cart': AddToCartSerializer(customer_cart, many=True).data,
                }, status=status.HTTP_200_OK
            )
            
        else:
            product_id = str(kwargs.get('pk'))
            # product_id = str(request.data.get('product'))
            session_cart = request.session.get('cart', {})
            if product_id not in session_cart:
                return Response(
                    {
                        'error': 'Product not found in cart!'
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            if action == 'increase':
                session_cart[product_id]["quantity"] += 1
            elif action == 'decrease':
                if session_cart[product_id]["quantity"] > 1:
                    session_cart[product_id]["quantity"] -= 1
                else:
                    del session_cart[product_id]
            else:
                return Response(
                    {
                        'error': 'Invalid Action! use "increase" or "decrease".',
                        'cart': session_cart,
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            
            request.session['cart'] = session_cart
            request.session.modified = True
            return Response(
                {
                    'message': 'Cart Updated!',
                    'cart': session_cart
                }, status=status.HTTP_200_OK
            )


     
        





class FreeAddToCartViewset(viewsets.ModelViewSet):
    queryset = FreeAddToCart.objects.all()
    serializer_class = FreeAddToCartSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_customer(self):
        try:
            return self.request.user.customer_authentication
        except Customer.DoesNotExist:
            return None
    
    def get_queryset(self):
        customer = self.get_customer()
        if customer:
            return FreeAddToCart.objects.filter(customer=customer)
        else:
            return FreeAddToCart.objects.none()
    


# Create your views here.
