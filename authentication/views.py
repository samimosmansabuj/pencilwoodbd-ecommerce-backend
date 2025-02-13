from .serializers import UserCreationSerializers, UserListSerializers
from rest_framework.generics import CreateAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework import permissions
from rest_framework.response import Response
from .models import CustomUser

class UserCreationViews(CreateAPIView):
    serializer_class = UserCreationSerializers
    permission_classes = [permissions.AllowAny]

class UserListViews(ListAPIView):
    queryset = CustomUser.objects.all()
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    serializer_class = UserListSerializers
    

class ProtectedView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.AllowAny]
    def get(self, request):
        return Response({"message": "You are authenticated!"})
