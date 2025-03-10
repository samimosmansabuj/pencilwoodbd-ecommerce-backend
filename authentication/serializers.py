from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import CustomUser, Customer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed

#=========================Admin User Creation Serializers Start========================
class AdminCreationSerializers(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'username', 'password', 'user_type']

class AdminTokenObtainPariSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if user.user_type == 'Customer':
            raise AuthenticationFailed("Only Admin, Super Admin or Staff can login!", code='authorization')
        return data
#=========================Admin User Creation Serializers End========================


#=========================Customer User Creation Serializers Start========================
class CustomerTokenObtainPariSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if user.user_type != 'Customer':
            raise AuthenticationFailed({
                    'status': False,
                    'message': 'Only Customer can login!'
                }, code='authorization')
        return data

class CustomerRegistrationSerializers(serializers.ModelSerializer):
    phone = serializers.CharField(required=True)
    name = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'name', 'phone', 'email', 'password']
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data['password'] = make_password(password)
        validated_data['username'] = validated_data['name'].lower()
        validated_data['user_type'] = 'Customer'
        user = CustomUser.objects.create(
            username = validated_data['username'],
            email = validated_data['email'],
            user_type = validated_data['user_type'],
            password = validated_data['password']
        )
        return user
#=========================Customer User Creation Serializers End========================


class UserListSerializers(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('__all__')


class CurrentUserProfileSerializers(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        exclude = ('password', 'last_login', 'is_superuser', 'is_staff', 'is_active', 'groups', 'user_permissions')


class CustomerProfileSerializers(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email']


