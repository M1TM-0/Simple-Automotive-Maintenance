from apps.chat.views import (
    ChatDetailView,
    ChatListView,
    ChatMessagesView,
    ChatOpenView,
    ChatReadView,
)
from django.urls import path

urlpatterns = [
    path("chats/", ChatListView.as_view(), name="chats"),
    path("chats/<int:workshop_id>/open/", ChatOpenView.as_view(), name="chat-open"),
    path("chats/<int:pk>/", ChatDetailView.as_view(), name="chat-detail"),
    path("chats/<int:pk>/messages/", ChatMessagesView.as_view(), name="chat-messages"),
    path("chats/<int:pk>/read/", ChatReadView.as_view(), name="chat-read"),
]
