import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from authentication.models import CustomUser


# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.user = self.scope['user']
#         if self.user.is_authenticated:
#             await self.close()
#             return
        
#         self.other_user_id = self.scope['url_router']['kwargs']['other_user_id']
#         self.room_name = f"chat_{min(self.user.id, self.other_user_id.id)}_{max(self.user.id, self.other_user_id.id)}"
#         self.room_group_name = f"chat_{self.room_name}"
        
#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         await self.accept()
    
#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
    
#     async def receive(self, text_data):
#         data = json.loads(text_data)
#         message = data['message']
        
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'chat_message',
#                 'message': message,
#                 'user': self.user.username
#             }
#         )
    
#     async def chat_message(self, event):
#         username = event['user']
#         message = event['message']
#         await self.send(text_data=json.dumps({
#             'message': message,
#             'user': username
#         }))







# consumers.py
import json
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from authentication.models import CustomUser
from .models import ChatMessage, CallRecording
from authentication.models import * 
from django.db.models import Q
from django.core.files.base import ContentFile
import base64
from datetime import timedelta
from django.utils import timezone
from .templatetags.chat_tags import chat_is_read_status


class Consumer(WebsocketConsumer):
    def connect(self):
        self.accept()
       
        self.send(text_data=json.dumps({
            'type': 'connection',
            'data': {
                'message': "Connected"
            }
        }))

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.my_name,
            self.channel_name
           
        )

    # Receive message from client WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        # print(text_data_json)

        eventType = text_data_json['type']

        if eventType == 'login':
            name = text_data_json['data']['name']
            receiver = text_data_json['data']['receiver']
               
            sender = CustomUser.objects.get(username=name)
            receiver = CustomUser.objects.get(username=receiver)
            chat = ChatMessage.objects.filter(
            (Q(sender=sender) & Q(receiver=receiver)) | 
            (Q(sender=receiver) & Q(receiver=sender))
            )
            
            # if chat.count() == 0:
            #         flag = f'flag_{name}{receiver}'
            # else:
            #         flag = chat.first().flag
             
            if(sender.role == 3):
                if chat.count() == 0:
                    flag = f'flag_{name}'
                else:
                    flag = chat.first().flag
            else:
                if chat.count() == 0:
                    flag = f'flag_{receiver}'
                else:
                    flag = f'flag_{receiver}'
                    
            if(receiver.role == 3):
                if chat.count() == 0:
                    flag = f'flag_{receiver}'
                else:
                    flag = chat.first().flag   
            else:
                if chat.count() == 0:
                    flag = f'flag_{name}'
                else:
                    flag = f'flag_{name}'                        

            # we will use this as room name as well
            self.my_name = name
            self.receiver = receiver
            self.room_group_name = flag
            
            print(self.room_group_name)

            # Join room
            async_to_sync(self.channel_layer.group_add)(
                self.my_name,
                self.channel_name
            )
            
            async_to_sync(self.channel_layer.group_add)(
                self.room_group_name,
                self.channel_name
            )
        
        if eventType == 'call':
            name = text_data_json['data']['name']
            print(self.my_name, "is calling", name);
            # print(text_data_json)
            
            async_to_sync(self.channel_layer.group_send)(
                name,
                {
                    'type': 'call_received',
                    'data': {
                        'caller': self.my_name,
                        'rtcMessage': text_data_json['data']['rtcMessage']
                    }
                }
            )

        if eventType == 'answer_call':
            # has received call from someone now notify the calling user
            # we can notify to the group with the caller name
            
            caller = text_data_json['data']['caller']
            # print(self.my_name, "is answering", caller, "calls.")

            async_to_sync(self.channel_layer.group_send)(
                caller,
                {
                    'type': 'call_answered',
                    'data': {
                        'rtcMessage': text_data_json['data']['rtcMessage']
                    }
                }
            )

        if eventType == 'ICEcandidate':

            user = text_data_json['data']['user']

            async_to_sync(self.channel_layer.group_send)(
                user,
                {
                    'type': 'ICEcandidate',
                    'data': {
                        'rtcMessage': text_data_json['data']['rtcMessage']
                    }
                }
            )
        
        if eventType == 'chat_message':
            async_to_sync(self.channel_layer.group_send)(
               self.room_group_name,
                {
                    'type': 'chat_message',
                    'data': text_data_json['data']
                }
            )
        
        if eventType == 'audio_message':
            self.handle_audio_message(text_data_json)
    
        message_type = text_data_json['type']

        if message_type == 'decline_call':
            self.decline_call(text_data_json['data'])
        elif message_type == 'end_call':
            self.end_call(text_data_json['data'])    
        
        
        if message_type == 'decline_call' or message_type == 'end_call':
            self.handle_end_or_decline_call(text_data_json)       
         
        if message_type == 'delete_all_messages':
            self.delete_all_messages(text_data_json['data'])   


    def call_received(self, event):

        # print(event)
        print('Call received by ', self.my_name )
        self.send(text_data=json.dumps({
            'type': 'call_received',
            'data': event['data']
        }))


    def call_answered(self, event):

        # print(event)
        print(self.my_name, "'s call answered")
        self.send(text_data=json.dumps({
            'type': 'call_answered',
            'data': event['data']
        }))


    def ICEcandidate(self, event):
        self.send(text_data=json.dumps({
            'type': 'ICEcandidate',
            'data': event['data']
        }))
        
        
    # def chat_message(self, event):
    #     # Send chat message data to WebSocket
    #     self.send(text_data=json.dumps({
    #         'type': 'chat_message',
    #         'data': event['data']
    #     }))
    def chat_message(self, event):
        # Extract the message data
        message_data = event['data']
        
        sender_username = message_data.get('sender')
        receiver_username = message_data.get('receiver')
        message = message_data.get('message')

        # Check if the current user is the sender
        if sender_username == self.scope["user"].username:
            # Save the chat message to the database
            self.save_chat_message(sender_username, receiver_username, message)
        if receiver_username == self.scope["user"].username:
            self.send_unread_count_update(receiver_username)
            print(f'rec {receiver_username}')
        self.send(text_data=json.dumps({
            'type': 'chat_message',
            'data': message_data
        }))

    def save_chat_message(self, sender_username, receiver_username, message):
        
        sender = CustomUser.objects.get(username=sender_username)
        receiver = CustomUser.objects.get(username=receiver_username)
        chat = ChatMessage.objects.filter(
            (Q(sender=sender) & Q(receiver=receiver)) | 
            (Q(sender=receiver) & Q(receiver=sender))
        )
        print(f'sender: {sender.username} {sender.role}')
        print(f'receiver: {receiver.username} {receiver.role}')
        
        # if chat.count() == 0:
        #     flag = f'flag_{sender_username}{receiver_username}'
        # else:
        #    flag = chat.first().flag
        if(sender.role == 3):
            user_chat = ChatMessage.objects.filter(flag=f'flag_{sender_username}')
            if user_chat.count() == 0:
                flag = f'flag_{sender_username}'
                # ChatMessage.objects.create(sender=sender, receiver=receiver, message=message, flag=flag)
                admin_flag = 'Flag'
            else:
                flag = user_chat.first().flag
                # user_chat = ChatMessage.objects.filter(sender=sender)
                if(user_chat.first().admin_flag == 'Flag'):
                   admin_flag = 'Flag'
                else:
                    admin_flag = user_chat.first().admin_flag
                    partner = CustomUser.objects.get(username=admin_flag)
                    receiver = partner
                       
        else:
            flag = f'flag_{receiver_username}'
            admin_flag=sender.username
            # ChatMessage.objects.create(sender=sender, receiver=receiver, message=message, flag=flag, admin_flag=sender.username)
                    
        
        if(receiver.role == 3):
            if chat.count() == 0:
                flag = f'flag_{receiver_username}'
                # ChatMessage.objects.create(sender=sender, receiver=receiver, message=message, flag=flag)
            else:
                flag = chat.first().flag
        
        ChatMessage.objects.create(sender=sender, receiver=receiver, message=message, flag=flag, admin_flag=admin_flag)
                
        

    
    def decline_call(self, data):
        # Notify the caller that the call was declined
        caller_channel_name = data['to']  # Assuming 'to' contains the caller's channel name
        self.channel_layer.group_send(
            caller_channel_name,
            {
                'type': 'send_message',
                'message': json.dumps({'type': 'call_declined', 'from': data['from']})
            }
        )

    def end_call(self, data):
        # Notify the receiver that the call was ended before being answered
        receiver_channel_name = data['to']  # Assuming 'to' contains the receiver's channel name
        self.channel_layer.group_send(
            receiver_channel_name,
            {
                'type': 'send_message',
                'message': json.dumps({'type': 'call_ended', 'from': data['from']})
            }
        )

    def send_message(self, event):
        message = event['message']
        self.send(text_data=message)
    
    
    # New method to forward 'decline_call' or 'end_call' messages
    def handle_end_or_decline_call(self, event):
        recipient = event['to']
        # Forward the message to the specified recipient
        async_to_sync(self.channel_layer.group_send)(
            recipient,
            {
                'type': 'websocket.send',
                'text': json.dumps({
                    'type': event['type'],
                    'from': self.scope['user'].username  # or however you identify users
                })
            }
        )      
        
        
    def delete_all_messages(self, data):
        # Delete all messages between the sender and receiver
        sender = CustomUser.objects.get(username=data['sender'])
        receiver = CustomUser.objects.get(username=data['receiver'])
        ChatMessage.objects.filter(
            (Q(sender=sender) & Q(receiver=receiver)) | 
            (Q(sender=receiver) & Q(receiver=sender))
            ).delete()

    def handle_audio_message(self, message):
        audio_data_base64 = message['data']
        caller_username = message['caller']
        receiver_username = message['receiver']
        otherUser = message['otherUser']
        duration = message.get('duration', 0)  # Duration in seconds, as an example

        if(caller_username==receiver_username):
            receiver_username = otherUser
        # Decode the Base64 audio data
        if ";base64," in audio_data_base64:
            header, audio_data_base64 = audio_data_base64.split(";base64,")
        audio_content = base64.b64decode(audio_data_base64)

        # Create a file object from the binary content
        audio_file = ContentFile(audio_content, name=f"call_recording_{caller_username}_{receiver_username}.ogg")  # You might want to generate a unique name

        # Fetch the caller and receiver User objects
        caller = CustomUser.objects.get(username=caller_username)
        receiver = CustomUser.objects.get(username=receiver_username)
        
        recording = CallRecording.objects.filter(
        (Q(caller=caller) & Q(receiver=receiver)) | 
        (Q(caller=receiver) & Q(receiver=caller))
        )
        
        if(caller.role == 3):
            if recording.count() == 0:
                flag = f'flag_{caller_username}'
            else:
                flag = recording.first().flag
        
        if(receiver.role == 3):
            if recording.count() == 0:
                flag = f'flag_{receiver_username}'
            else:
                flag = recording.first().flag   

        # Create and save the CallRecording model instance
        call_recording = CallRecording(
            caller=caller,
            receiver=receiver,
            recording=audio_file,
            duration=timedelta(seconds=duration),
            timestamp=timezone.now(),
            flag=flag
        )
        call_recording.save()
    

        file_url = call_recording.recording.url  # Get the URL of the saved file

        # Constructing the WebSocket response
        response_data = {
            'type': 'call_recording_saved',
            'file_url': file_url,
        }

        # Sending the response
        self.send(text_data=json.dumps(response_data))


        print(f"Saved call recording from {caller_username} to {receiver_username}")
    
    
    
    # def new_message_notification(self, event):
    #     # Call the utility function to get the count of unread messages
    #     unread_count = chat_is_read_status(self.scope["user"])
    #     print(unread_count)
    #     # Send the unread message count to the client
    #     self.send(text_data=json.dumps({
    #         'type': 'new_message_notification',
    #         'unread_count': unread_count
    #     }))
    
    def get_unread_messages_count(self, username):
        user = CustomUser.objects.get(username=username)
        return chat_is_read_status(user)

    def send_unread_count_update(self, username):
        unread_count = self.get_unread_messages_count(username)
        # Constructing the WebSocket response
        response_data = {
            'type': 'new_message_notification',
            'unread_count': unread_count
        }

        # Sending the response to the client
        self.send(text_data=json.dumps(response_data))


