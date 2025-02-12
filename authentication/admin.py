from django.contrib import admin
from .models import Customer, CustomUser, Role

admin.site.register(CustomUser)
admin.site.register(Customer)
admin.site.register(Role)