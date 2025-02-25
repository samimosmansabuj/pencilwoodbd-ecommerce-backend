from django.contrib import admin
from .models import ChatMessage, CallRecording

admin.site.register(ChatMessage)
admin.site.register(CallRecording)
