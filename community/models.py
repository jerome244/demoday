from __future__ import annotations

import io
import zipfile
from datetime import timedelta
import uuid

import jwt
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Q

# -------------------------
# Users & Notifications
# -------------------------

class User(AbstractUser):
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True, null=True)  # <-- allow NULL
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    profile_photo = models.ImageField(upload_to="profiles/", null=True, blank=True)
    blocked = models.BooleanField(default=False)
    # When using AbstractUser, password hashing is built-in (set_password/check_password)

    def display_info(self) -> str:
        return (
            f"ID: {self.pk}, Name: {self.name or self.username}, "
            f"Email: {self.email}, Age: {self.age}, "
            f"Created on: {timezone.localtime(self.date_joined)}"
        )

    def block(self) -> str:
        if not self.blocked:
            self.blocked = True
            self.save(update_fields=["blocked"])
            Notification.objects.create(user=self, message=f"{self.name or self.username} has been blocked.")
        return f"{self.name or self.username} has been blocked."

    def unblock(self) -> str:
        if not self.blocked:
            return f"{self.name or self.username} is not blocked."
        self.blocked = False
        self.save(update_fields=["blocked"])
        Notification.objects.create(user=self, message=f"{self.name or self.username} has been unblocked.")
        return f"{self.name or self.username} has been unblocked."

    def add_notification(self, message: str) -> None:
        Notification.objects.create(user=self, message=message)

    def view_notifications(self) -> str:
        qs = self.notifications.order_by("-created_at")
        if not qs.exists():
            return f"No notifications for {self.name or self.username}."
        return "\n".join(n.message for n in qs)

    # Optional JWT helper to mirror your original code (for APIs, prefer simplejwt)
    def generate_jwt(self) -> str:
        payload = {
            "id": self.pk,
            "name": self.name or self.username,
            "email": self.email,
            "exp": timezone.now() + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        return token

    class Meta:
        constraints = [
            # Unique only when email is present (not NULL/empty)
            models.UniqueConstraint(
                fields=["email"],
                condition=Q(email__isnull=False) & ~Q(email=""),
                name="unique_user_email_not_blank",
            )
        ]


class Notification(models.Model):
    user = models.ForeignKey(User, related_name="notifications", on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Notif({self.user_id}): {self.message[:40]}..."


# -------------------------
# Forum: Threads & Messages
# -------------------------

class Thread(models.Model):
    title = models.CharField(max_length=255)
    participants = models.ManyToManyField(User, related_name="threads")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title

    @transaction.atomic
    def add_message(self, sender: User, content: str) -> "Message":
        msg = Message.objects.create(thread=self, sender=sender, content=content)
        # Notify participants except the sender
        others = self.participants.exclude(pk=sender.pk)
        for p in others:
            p.add_notification(f"New message in thread '{self.title}' by {sender.name or sender.username}: {content}")
        return msg


class Message(models.Model):
    thread = models.ForeignKey(Thread, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name="messages", on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name="liked_messages", blank=True)

    def __str__(self) -> str:
        return f"{self.timestamp} - {self.sender}: {self.content[:50]}"

    def like(self, user: User) -> str:
        if not self.likes.filter(pk=user.pk).exists():
            self.likes.add(user)
            self.sender.add_notification(f"{user.name or user.username} liked your message: {self.content}")
            return f"{user.name or user.username} liked the message."
        return f"{user.name or user.username} has already liked this message."

    def unlike(self, user: User) -> str:
        if self.likes.filter(pk=user.pk).exists():
            self.likes.remove(user)
            return f"{user.name or user.username} unliked the message."
        return f"{user.name or user.username} has not liked this message."


# -------------------------
# Private Conversations
# -------------------------

class Conversation(models.Model):
    title = models.CharField(max_length=255, default="Private Conversation")
    user1 = models.ForeignKey(User, related_name="conversations_as_user1", on_delete=models.CASCADE)
    user2 = models.ForeignKey(User, related_name="conversations_as_user2", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Prevent duplicated pairs (user1,user2) and (user2,user1)
            models.UniqueConstraint(fields=["user1", "user2"], name="unique_conversation_pair")
        ]

    def __str__(self) -> str:
        return f"{self.title}: {self.user1} ↔ {self.user2}"

    @transaction.atomic
    def add_message(self, sender: User, content: str) -> "PrivateMessage":
        # FIX: ensure sender is part of the conversation
        if sender.pk not in (self.user1_id, self.user2_id):
            raise ValueError("Sender must be participant of the conversation.")
        receiver = self.user2 if sender.pk == self.user1_id else self.user1
        pm = PrivateMessage.objects.create(conversation=self, sender=sender, receiver=receiver, content=content)
        receiver.add_notification(f"New message in '{self.title}' by {sender.name or sender.username}: {content}")
        return pm


class PrivateMessage(models.Model):
    conversation = models.ForeignKey(Conversation, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name="sent_private_messages", on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name="received_private_messages", on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name="liked_private_messages", blank=True)

    def __str__(self) -> str:
        return f"{self.timestamp} - {self.sender} → {self.receiver}: {self.content[:50]}"

    def like(self, user: User) -> str:
        if not self.likes.filter(pk=user.pk).exists():
            self.likes.add(user)
            self.sender.add_notification(f"{user.name or user.username} liked your private message: {self.content}")
            return f"{user.name or user.username} liked the message."
        return f"{user.name or user.username} has already liked this message."

    def unlike(self, user: User) -> str:
        if self.likes.filter(pk=user.pk).exists():
            self.likes.remove(user)
            return f"{user.name or user.username} unliked the message."
        return f"{user.name or user.username} has not liked this message."


# -------------------------
# Projects & “Files”
# -------------------------

class Project(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    creator = models.ForeignKey(User, related_name="created_projects", on_delete=models.CASCADE)
    participants = models.ManyToManyField(User, related_name="projects", blank=True)
    liked_by = models.ManyToManyField(User, related_name="liked_projects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ManyToManyField("community.User", related_name="saved_projects", blank=True)

    def __str__(self) -> str:
        return self.name

    def display_project_info(self) -> str:
        participants = ", ".join(u.name or u.username for u in self.participants.all())
        return (
            f"Name: {self.name}\n"
            f"Description: {self.description}\n"
            f"Creator: {self.creator.display_info()}\n"
            f"Participants: {participants or '-'}"
        )

    def add_participant(self, user: User) -> str:
        if not self.participants.filter(pk=user.pk).exists():
            self.participants.add(user)
            user.add_notification(f"You have been added to the project '{self.name}' by {self.creator.name or self.creator.username}.")
            self.creator.add_notification(f"{user.name or user.username} has been added to the project '{self.name}'.")
            return f"{user.name or user.username} has been added to the project."
        return f"{user.name or user.username} is already a participant."

    def remove_participant(self, user: User) -> str:
        if self.participants.filter(pk=user.pk).exists():
            self.participants.remove(user)
            return f"{user.name or user.username} removed from the project."
        return f"{user.name or user.username} is not a participant."

    def like(self, user: User) -> str:
        if self.liked_by.filter(pk=user.pk).exists():
            return f"{user.name or user.username} has already liked the project."
        self.liked_by.add(user)
        # NEW: notify owner on like (skip self-like notify)
        if user != self.creator:
            self.creator.add_notification(f"{user.name or user.username} liked your project '{self.name}'.")
        return f"{user.name or user.username} liked the project '{self.name}'."

    def unlike(self, user: User) -> str:
        if not self.liked_by.filter(pk=user.pk).exists():
            return f"{user.name or user.username} has not liked the project yet."
        self.liked_by.remove(user)
        # OPTIONAL: notify owner on unlike (comment out if undesired)
        if user != self.creator:
            self.creator.add_notification(f"{user.name or user.username} unliked your project '{self.name}'.")
        return f"{user.name or user.username} unliked the project '{self.name}'."

    def delete_with_notifications(self) -> None:
        creator = self.creator
        name = self.name
        parts = list(self.participants.all())
        self.delete()
        creator.add_notification(f"The project '{name}' has been deleted.")
        for p in parts:
            if p != creator:
                p.add_notification(f"The project '{name}' has been deleted.")

    # ---- ZIP helpers (store text files in DB) ----

    def add_text_file(self, path: str, content: str) -> "ProjectFile":
        return ProjectFile.objects.update_or_create(
            project=self, path=path, defaults={"content": content}
        )[0]

    def get_file_content(self, path: str) -> str | None:
        pf = self.files.filter(path=path).first()
        return pf.content if pf else None

    def project_tree(self) -> list[str]:
        return list(self.files.values_list("path", flat=True))

    def as_zip_bytes(self) -> bytes:
        """
        Produce a ZIP of all ProjectFile rows as in-memory bytes.
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in self.files.all():
                zf.writestr(f.path, f.content or "")
        buffer.seek(0)
        return buffer.read()

    def ingest_zip(self, uploaded_file) -> int:
        """
        Read an uploaded zip file (InMemoryUploadedFile/TemporaryUploadedFile),
        store each member as a ProjectFile row. Returns number of files ingested.
        """
        count = 0
        with zipfile.ZipFile(uploaded_file) as zf:
            for name in zf.namelist():
                if name.endswith("/"):  # skip folders
                    continue
                data = zf.read(name)
                # We assume text files; adapt if you want binary files
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    # store binary as base64 or skip; here we skip to keep parity with your text-only approach
                    continue
                self.add_text_file(name, text)
                count += 1
        return count

    # convenience methods
    def save_for(self, user):
        if not self.saved_by.filter(pk=user.pk).exists():
            self.saved_by.add(user)
            return f"{user.name or user.username} saved project '{self.name}'."
        return f"{user.name or user.username} already saved this project."

    def unsave_for(self, user):
        if self.saved_by.filter(pk=user.pk).exists():
            self.saved_by.remove(user)
            return f"{user.name or user.username} removed saved project '{self.name}'."
        return f"{user.name or user.username} had not saved this project."


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, related_name="files", on_delete=models.CASCADE)
    path = models.CharField(max_length=512)  # e.g., "src/app.py"
    content = models.TextField(blank=True)

    class Meta:
        unique_together = (("project", "path"),)

    def __str__(self) -> str:
        return f"{self.project.name}:{self.path}"


class ProjectInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        REVOKED = "REVOKED", "Revoked"

    project = models.ForeignKey(Project, related_name="invitations", on_delete=models.CASCADE)
    inviter = models.ForeignKey("community.User", related_name="sent_project_invitations", on_delete=models.CASCADE)
    invitee = models.ForeignKey("community.User", related_name="received_project_invitations", on_delete=models.CASCADE)
    message = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # only one *pending* invite per (project, invitee)
            models.UniqueConstraint(
                fields=["project", "invitee"],
                condition=Q(status="PENDING"),
                name="unique_pending_invite_per_project_invitee",
            )
        ]

    def __str__(self):
        return f"Invite({self.project.name} → {self.invitee} : {self.status})"

    # Domain helpers
    def accept(self, actor):
        if actor != self.invitee and not actor.is_staff:
            raise PermissionError("Only the invitee (or staff) can accept.")
        if self.status != self.Status.PENDING:
            raise ValueError("Invitation is not pending.")
        self.status = self.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])
        self.project.add_participant(self.invitee)
        self.inviter.add_notification(f"{self.invitee} accepted your invitation to '{self.project.name}'.")
        self.invitee.add_notification(f"You joined project '{self.project.name}'.")

    def decline(self, actor):
        if actor != self.invitee and not actor.is_staff:
            raise PermissionError("Only the invitee (or staff) can decline.")
        if self.status != self.Status.PENDING:
            raise ValueError("Invitation is not pending.")
        self.status = self.Status.DECLINED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])
        self.inviter.add_notification(f"{self.invitee} declined your invitation to '{self.project.name}'.")

    def revoke(self, actor):
        is_owner = actor == self.inviter or actor == self.project.creator or actor.is_staff
        if not is_owner:
            raise PermissionError("Only inviter, project creator, or staff can revoke.")
        if self.status != self.Status.PENDING:
            raise ValueError("Invitation is not pending.")
        self.status = self.Status.REVOKED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at"])
        self.invitee.add_notification(f"Your invitation to '{self.project.name}' was revoked.")
