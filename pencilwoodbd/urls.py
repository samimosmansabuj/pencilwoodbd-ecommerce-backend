import os
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve as static_serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('authentication.urls')),
    path('', include('live_chat.urls')),
    path('', include('product.urls')),
    path('', include('order.urls')),
    path('site/', include('site_app.urls')),
    path('', include('marketing.urls')),
    
    path('', include('dashbaord.urls')),
]

SERVE_MEDIA = os.getenv("SERVE_MEDIA", "False").strip().lower() in ("true","1","yes")

if SERVE_MEDIA:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
        re_path(r'^static/(?P<path>.*)$', static_serve, {'document_root': settings.STATIC_ROOT}),
    ]