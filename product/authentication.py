from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.signals import user_logged_in
from rest_framework.exceptions import AuthenticationFailed

class CustomJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        user_auth_tuple = super().authenticate(request)
        if user_auth_tuple is not None:
            user, token = user_auth_tuple
            user_logged_in.send(sender=user.__class__, request=request, user=user)
            return user, token
        return None
