from django.shortcuts import render
from .serializers import CategorySerializer, ProductSerializer, AddToCartSerializer, FreeAddToCartSerializer
from rest_framework import viewsets, permissions
from rest_framework.response import Response
from .models import Category, Product, AddToCart, FreeAddToCart

class AdminCreationPermision(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff

class CategoryViewset(viewsets.ModelViewSet):
    queryset = Category.objects.all()

# Create your views here.
