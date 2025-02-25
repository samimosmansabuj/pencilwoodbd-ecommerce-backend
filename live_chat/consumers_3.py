import json
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import ChatMessage
from rest_framework.exceptions import AuthenticationFailed
from django.utils.timezone import now

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = self.scope['query_string'].decode().split('=')[1]
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            self.user = await self.get_user(user_id)
        except Exception as e:
            await self.close()
            return
        
        self.room_group_name = f"chat_{self.user.id}"
        await self.channel_layer.group_add(
            self.room_group_name, self.channel_name
        )
        
        await self.accept()
    
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name, self.channel_name
        )

    
    
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        receiver_id = text_data_json['receiver']
        
        receiver = await self.get_user(receiver_id)
        
        chat_message = await self.save_message(self.user, receiver, message)

        receiver_room_name = f"chat_{receiver_id}"
        await self.channel_layer.group_send(
            # self.room_group_name,
            receiver_room_name,
            {
                'type': 'chat_message',
                'message': chat_message.message,
                'sender': chat_message.sender.username,
                'receiver': chat_message.receiver.username,
                'timestamp': chat_message.timestamp.isoformat(),
            }
        )
    
    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps({
                'message': event['message'],
                'sender': event['sender'],
                'receiver': event['receiver'],
            })
        )
    
    
    @database_sync_to_async
    def get_user(self, user_id):
        return get_user_model().objects.get(id=user_id)
    
    
    @staticmethod
    @database_sync_to_async
    def save_message(sender, receiver, message):
        return ChatMessage.objects.create(
            sender = sender,
            receiver = receiver,
            message = message,
        )

