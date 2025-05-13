from .serializers import AdminCreationSerializers, UserListSerializers, CustomerRegistrationSerializers, CustomerTokenObtainPariSerializer, AdminTokenObtainPariSerializer, CurrentUserProfileSerializers, CustomerProfileSerializers, CustomLogoutSerializer
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework import permissions
from rest_framework.response import Response
from .models import CustomUser, Customer
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import NotAuthenticated, ValidationError, AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from order.models import Order, Address
from order.serializers import OrderListSerializers, AddressSerializers
from .utils import CustomTokenObtainPairView
# from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

    
#========================Admin User Creation Views Start=======================
class AdminCreationViews(CreateAPIView):
    serializer_class = AdminCreationSerializers
    permission_classes = [permissions.AllowAny]

# class AdminTokenObtainPairViews(TokenObtainPairView):
class AdminTokenObtainPairViews(CustomTokenObtainPairView):
    serializer_class = AdminTokenObtainPariSerializer

#=========================Admin User Creation Views End========================


class UserListViews(ListAPIView):
    queryset = CustomUser.objects.all()
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    serializer_class = UserListSerializers
    
class ProtectedView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.AllowAny]
    def get(self, request):
        return Response({"message": "You are authenticated!"})


#=========================Customer User Creation Views Start========================
class CustomerRegistrationViews(CreateAPIView):
    serializer_class = CustomerRegistrationSerializers
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            
            Customer.objects.create(
                user=user, name=request.data['name'], email=request.data['email'], phone=request.data['phone']
            ).save()
            return Response(
                {
                    'message': 'Registration Successfully!'
                }, status=status.HTTP_201_CREATED
            )
        except ValidationError:
            error_json = {kay: value[0] for kay, value in serializer.errors.items()}
            return Response({
                'status': False,
                'message': 'Registration Unsuccessfull!',
                'error': error_json
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'status': False,
                'message': 'Somethings Wrong!',
                'error': str(e)
            })


class CustomerTokenObtainPairViews(TokenObtainPairView):
    serializer_class = CustomerTokenObtainPariSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            return Response({
                'status': True,
                'message': 'Login Successfully!',
                'token': serializer.validated_data
            }, status=status.HTTP_200_OK)
        except ValidationError:
            error_json = {kay: value[0] for kay, value in serializer.errors.items()}
            return Response({
                'status': False,
                'message': 'Login Unsuccessful!',
                'error': error_json
            }, status=status.HTTP_400_BAD_REQUEST)
        except AuthenticationFailed as e:
            return Response(
                {
                    'status': False,
                    'message': 'Authentication Field!',
                    'error': str(e)
                }, status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            return Response({
                'status': False,
                'message': 'Somethings wrong!',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class CustomLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        try:
            serializer = CustomLogoutSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                {
                    'status': True,
                    'message': 'Logout Successful!',
                }, status=status.HTTP_205_RESET_CONTENT
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    'status': False,
                    'message': 'Logout Failed!',
                    'error': error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'message': 'Something Wrong!',
                    'error': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

#=========================Customer User Creation Views End========================
class CurrentUserDetails(RetrieveAPIView):
    serializer_class = CurrentUserProfileSerializers
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def handle_exception(self, exc):
        if isinstance(exc, NotAuthenticated):
            return Response({
                'status': False,
                'message': 'Authentication credentials were not provided.'
            }, status=status.HTTP_401_UNAUTHORIZED)
        return super().handle_exception(exc)
    
    def get(self, request, *args, **kwargs):
        try:
            user = self.get_object()
            customer = user.customer_authentication
            order = Order.objects.filter(
                customer=customer
            )
            address = Address.objects.filter(
                customer=customer
            )
            customer_data = CustomerProfileSerializers(customer).data
            order_data = OrderListSerializers(order, many=True).data
            address_data = AddressSerializers(address, many=True).data
            serializer = self.get_serializer(user).data
            return Response({
                'status': True,
                'data': serializer,
                'profile': customer_data,
                'user_order': order_data,
                'user_address': address_data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': False,
                'message': 'Somethings wrong!',
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
     


