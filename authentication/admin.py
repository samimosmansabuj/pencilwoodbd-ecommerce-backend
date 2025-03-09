from django.contrib import admin
from .models import Customer, CustomUser, Role
from django.contrib.sessions.models import Session
from django.contrib.auth.admin import UserAdmin


# class CustomUserAdmin(UserAdmin):
#     list_display = ('email', 'username', 'user_type', 'created_at', 'updated_at')
#     search_fields = ('email', 'username')
#     ordering = ('email',)

# admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(CustomUser)
admin.site.register(Customer)
admin.site.register(Role)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ["session_key", "get_decoded_data", "expire_date"]
    search_fields = ["session_key"]
    ordering = ["-expire_date"]

    def get_decoded_data(self, obj):
        """Display decoded session data in the admin panel."""
        return obj.get_decoded()

    get_decoded_data.short_description = "Session Data"
