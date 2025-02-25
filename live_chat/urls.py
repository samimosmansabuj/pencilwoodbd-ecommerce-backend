from django.urls import path, include
from .views import user_list, chat_history, send_message

urlpatterns = [
    path('user-list/', user_list, name='user-list'),
    path('chat/<int:user_id>/', chat_history, name='chat_history'),
    path('send_message/<int:user_id>/', send_message, name='send_message'),
]