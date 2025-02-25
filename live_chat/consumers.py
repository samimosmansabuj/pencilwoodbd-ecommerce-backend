# chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from .models import ChatMessage
from channels.db import database_sync_to_async
from datetime import datetime

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Ensure user is authenticated before allowing the WebSocket connection
        if self.scope["user"].is_authenticated:
            self.user_id = self.scope['url_route']['kwargs']['user_id']
            self.room_group_name = f'chat_{self.user_id}'

            # Accept WebSocket connection
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        else:
            # Reject WebSocket connection if not authenticated
            await self.close()

    async def disconnect(self, close_code):
        # Leave the group on disconnect
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        # Ensure user is authenticated before processing the message
        if not self.scope["user"].is_authenticated:
            return

        # Receive message from WebSocket
        data = json.loads(text_data)
        message = data['message']
        
        # Save the message to the database
        await self.save_message(message)
        
        # Send message to WebSocket
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message
            }
        )

    async def chat_message(self, event):
        # Send the chat message to WebSocket
        message = event['message']
        await self.send(text_data=json.dumps({
            'message': message
        }))

    @database_sync_to_async
    def save_message(self, message):
        # Save the message to the database
        ChatMessage.objects.create(
            sender=self.scope['user'],
            receiver_id=self.user_id,
            message=message,
            timestamp=datetime.now(),
            is_read=False
        )
