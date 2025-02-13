from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import CustomUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

class UserCreationSerializers(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'username', 'password', 'user_type']


class UserListSerializers(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('__all__')

