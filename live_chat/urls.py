from django.urls import path, include
from .views import chat

urlpatterns = [
    path('chat/', chat, name='chat_page')
]