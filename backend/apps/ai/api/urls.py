from django.urls import path
from .views import ChatView, ChatFeedbackView, ConversationListView, ConversationDetailView, SummaryTaskView


app_name = "ai"

urlpatterns = [
    path('summaries/<uuid:summary_id>/', SummaryTaskView.as_view(), name='summary-task'),
    path('conversations/', ConversationListView.as_view(), name='conversations'),
    path('conversations/<uuid:conversation_id>/', ConversationDetailView.as_view(), name='conversation-detail'),
    path('chat/', ChatView.as_view(), name='chat'),
    path('chat/<uuid:answer_id>/feedback/', ChatFeedbackView.as_view(), name='chat-feedback'),
]
