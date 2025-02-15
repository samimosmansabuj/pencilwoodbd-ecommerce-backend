from .serializers import AdminCreationSerializers, UserListSerializers, CustomerRegistrationSerializers, CustomerTokenObtainPariSerializer, AdminTokenObtainPariSerializer
from rest_framework.generics import CreateAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework import permissions
from rest_framework.response import Response
from .models import CustomUser, Customer
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView


    
#=========================Admin User Creation Views Start========================
class AdminCreationViews(CreateAPIView):
    serializer_class = AdminCreationSerializers
    permission_classes = [permissions.AllowAny]

class AdminTokenObtainPairViews(TokenObtainPairView):
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
        
class CustomerTokenObtainPairViews(TokenObtainPairView):
    serializer_class = CustomerTokenObtainPariSerializer
    
#=========================Customer User Creation Views End========================

