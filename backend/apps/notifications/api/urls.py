from django.urls import path
from .views import InboxView, ReadView, ReadAllView, TargetView, TicketView

urlpatterns = [
    path('', InboxView.as_view()),
    path('read-all/', ReadAllView.as_view()),
    path('ws-ticket/', TicketView.as_view()),
    path('<uuid:notice_id>/read/', ReadView.as_view()),
    path('<uuid:notice_id>/target/', TargetView.as_view()),
]
