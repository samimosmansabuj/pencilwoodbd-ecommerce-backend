from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('authentication.urls')),
    path('', include('live_chat.urls')),
    path('product/', include('product.urls')),
    path('order/', include('order.urls')),
]
