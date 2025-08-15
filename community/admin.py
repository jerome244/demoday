from django.contrib import admin
from .models import (
    User, Notification, Thread, Message,
    Conversation, PrivateMessage, Project, ProjectFile
)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "name", "email", "blocked", "is_staff", "is_superuser")
    list_filter = ("blocked", "is_staff", "is_superuser")
    search_fields = ("username", "name", "email")

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "message", "created_at", "read")
    list_filter = ("read",)
    search_fields = ("message", "user__username")

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at")
    filter_horizontal = ("participants",)
    inlines = [MessageInline]

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user1", "user2", "created_at")

@admin.register(PrivateMessage)
class PrivateMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "receiver", "timestamp")
    search_fields = ("content",)

class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 0

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "creator", "created_at")
    filter_horizontal = ("participants", "liked_by")
    inlines = [ProjectFileInline]

@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "path")
    search_fields = ("path", "project__name")
