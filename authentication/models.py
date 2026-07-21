from django.db import models
from django.contrib.auth.models import AbstractUser
from pencilwoodbd.choices import USER_TYPE

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, blank=True, null=True)  # made optional — phone customers won't have one
    phone = models.CharField(max_length=20, unique=True, blank=True, null=True)  # NEW: login key for storefront customers
    user_type = models.CharField(max_length=20, choices=USER_TYPE.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Dashboard/staff users keep using email (USERNAME_FIELD only matters for createsuperuser /
    # admin login; storefront phone-login has its own APIView below and doesn't use this).
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email or self.phone or self.username


class Customer(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='customer_profile')
    company = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, unique=True)  # CHANGED: unique — this is now the identity key
    second_phone = models.CharField(max_length=20, blank=True, null=True)
    whatsapp = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(max_length=200, blank=True, null=True)
    source = models.CharField(max_length=100, blank=True, null=True, default='Others')
    has_password = models.BooleanField(default=False)  # NEW: quick check without hitting user table

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=255, unique=True)
    can_read = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

