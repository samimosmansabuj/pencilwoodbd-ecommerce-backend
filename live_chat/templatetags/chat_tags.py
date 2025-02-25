from django import template
# from ..models import User, ChatMessage
from django.db.models import Q
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
# from civil_dashboard.models import Civil_ChatMessage, Civil_CallRecording
from live_chat.models import ChatMessage, CallRecording
from authentication.models import CustomUser 

register = template.Library()

@register.simple_tag()
# def otp_mail(user, otp, subject, status):
#         message = render_to_string('otp_email.txt', {
#             'user': user,
#             'otp': otp,
#             'status': status,
#         })
#         subject = subject
#         from_email = settings.EMAIL_HOST_USER
#         recipient_list = [user.email]
#         send_mail(subject, message, from_email, recipient_list)
        

@register.simple_tag()
def chat_is_read_status(username, model):
    user = CustomUser.objects.get(username=username)
    result = model.objects.filter(receiver=user, is_read=False).count()
    return result 
  

@register.simple_tag()
def chat_is_read_status2(receiver_username, sender_username):
    receiver = CustomUser.objects.get(username=receiver_username)
    sender = CustomUser.objects.get(username=sender_username)
    result = ChatMessage.objects.filter(receiver=receiver, sender=sender, is_read=False).count()
    return result

   