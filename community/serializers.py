from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Notification, Thread, Message, Conversation, PrivateMessage, Project, ProjectFile
from .models import ProjectInvitation

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("id", "username", "name", "email", "age", "profile_photo", "blocked", "password")
        read_only_fields = ("blocked",)

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)  # <-- hashes password
        else:
            user.set_password(User.objects.make_random_password())
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)  # <-- hashes on update too
        instance.save()
        return instance

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "message", "created_at", "read")

class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.PrimaryKeyRelatedField(read_only=True)
    likes_count = serializers.IntegerField(source="likes.count", read_only=True)

    class Meta:
        model = Message
        fields = ("id", "thread", "sender", "content", "timestamp", "likes_count")
        read_only_fields = ("timestamp", "likes_count")

class ThreadSerializer(serializers.ModelSerializer):
    participants = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Thread
        fields = ("id", "title", "participants", "created_at", "messages")
        read_only_fields = ("created_at",)

class PrivateMessageSerializer(serializers.ModelSerializer):
    sender = serializers.PrimaryKeyRelatedField(read_only=True)
    receiver = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PrivateMessage
        fields = ("id", "conversation", "sender", "receiver", "content", "timestamp")
        read_only_fields = ("timestamp",)

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ("id", "title", "user1", "user2", "created_at")
        read_only_fields = ("created_at",)

class ProjectFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectFile
        fields = ("id", "path", "content")

class ProjectSerializer(serializers.ModelSerializer):
    participants = serializers.PrimaryKeyRelatedField(queryset=Project.participants.rel.model.objects.all(), many=True, required=False)
    liked_by = serializers.PrimaryKeyRelatedField(queryset=Project.liked_by.rel.model.objects.all(), many=True, required=False)
    files = ProjectFileSerializer(many=True, read_only=True)

    # ✅ counts (read-only)
    saved_count = serializers.IntegerField(source="saved_by.count", read_only=True)
    liked_count = serializers.IntegerField(source="liked_by.count", read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "description",
            "creator",
            "participants",
            "liked_by",
            "created_at",
            "files",
            # add the declared fields:
            "saved_count",
            "liked_count",
        )
        read_only_fields = ("created_at", "saved_count", "liked_count")

    def create(self, validated_data):
        participants = validated_data.pop("participants", [])
        liked_by = validated_data.pop("liked_by", [])
        project = Project.objects.create(**validated_data)
        if participants:
            project.participants.add(*participants)
        if liked_by:
            project.liked_by.add(*liked_by)
        return project

    def update(self, instance, validated_data):
        participants = validated_data.pop("participants", None)
        liked_by = validated_data.pop("liked_by", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if participants is not None:
            instance.participants.set(participants)
        if liked_by is not None:
            instance.liked_by.set(liked_by)
        return instance    
class ProjectInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectInvitation
        fields = ("id", "project", "inviter", "invitee", "message", "status", "token", "created_at", "responded_at")
        read_only_fields = ("status", "token", "created_at", "responded_at", "inviter", "project")
        
            