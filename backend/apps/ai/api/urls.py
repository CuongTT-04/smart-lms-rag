from django.urls import path
from .views import ChatView, ChatFeedbackView


app_name = "ai"

urlpatterns = [
    path('chat/', ChatView.as_view(), name='chat'),
    path('chat/<uuid:answer_id>/feedback/', ChatFeedbackView.as_view(), name='chat-feedback'),
]
