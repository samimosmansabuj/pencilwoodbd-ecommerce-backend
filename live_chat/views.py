# views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import ChatMessage
from authentication.models import CustomUser
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now

# View to display all users to the current logged-in user
@login_required
def user_list(request):
    users = CustomUser.objects.exclude(id=request.user.id)  # Exclude the current user from the list
    return render(request, 'user_list.html', {'users': users})

# View to display chat history between current user and the selected user
@login_required
def chat_history(request, user_id):
    chat_history = ChatMessage.objects.filter(
        sender=request.user, receiver_id=user_id
    ) | ChatMessage.objects.filter(sender_id=user_id, receiver=request.user)
    chat_history = chat_history.order_by('timestamp')
    return render(request, 'chat_history.html', {'chat_history': chat_history, 'user_id': user_id})

# View to send a message to another user
@login_required
@api_view(['POST'])
def send_message(request, user_id):
    # Ensure the user is authenticated before processing the message
    if not request.user.is_authenticated:
        return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

    receiver = CustomUser.objects.get(id=user_id)
    message = request.data.get('message')

    if not message:
        return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Create new message and save to DB
    ChatMessage.objects.create(
        sender=request.user,
        receiver=receiver,
        message=message,
        timestamp=now()
    )

    return Response({'success': 'Message sent successfully.'}, status=status.HTTP_201_CREATED)
