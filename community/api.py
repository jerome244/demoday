import io
import json
from django.http import FileResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from .models import ProjectInvitation
from .models import Project, ProjectFile, Thread, Message, Conversation, PrivateMessage
from .serializers import (
    UserSerializer, NotificationSerializer, ThreadSerializer, MessageSerializer,
    ConversationSerializer, PrivateMessageSerializer, ProjectSerializer, ProjectFileSerializer, ProjectInvitationSerializer
)
from .permissions import NotBlocked, IsCreatorOrReadOnly, IsThreadParticipant, IsConversationParticipant
from rest_framework.exceptions import PermissionDenied

User = get_user_model()

# ---------- Users ----------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = [NotBlocked]

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser, NotBlocked])
    def block(self, request, pk=None):
        user = self.get_object()
        return Response({"detail": user.block()})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser, NotBlocked])
    def unblock(self, request, pk=None):
        user = self.get_object()
        return Response({"detail": user.unblock()})

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, NotBlocked])
    def notifications(self, request, pk=None):
        user = self.get_object()
        ser = NotificationSerializer(user.notifications.order_by("-created_at"), many=True)
        return Response(ser.data)

# ---------- Projects ----------
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = (
        Project.objects.all()
        .select_related("creator")
        .prefetch_related("participants", "liked_by", "saved_by", "files", "invitations")
    )
    serializer_class = ProjectSerializer
    permission_classes = [NotBlocked, IsCreatorOrReadOnly]

    # -------- participants --------
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def add_participant(self, request, pk=None):
        project = self.get_object()
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "user_id required"}, status=400)
        user = get_object_or_404(User, pk=user_id)
        msg = project.add_participant(user)
        return Response({"detail": msg})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def remove_participant(self, request, pk=None):
        project = self.get_object()
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "user_id required"}, status=400)
        user = get_object_or_404(User, pk=user_id)
        msg = project.remove_participant(user)
        return Response({"detail": msg})

    # -------- likes --------
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def like(self, request, pk=None):
        project = self.get_object()
        return Response({"detail": project.like(request.user)})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def unlike(self, request, pk=None):
        project = self.get_object()
        return Response({"detail": project.unlike(request.user)})

    # -------- save/unsave (bookmarks) --------
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def save(self, request, pk=None):
        project = self.get_object()
        return Response({"detail": project.save_for(request.user)})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def unsave(self, request, pk=None):
        project = self.get_object()
        return Response({"detail": project.unsave_for(request.user)})

    @action(detail=False, methods=["get"], url_path="saved/me", permission_classes=[IsAuthenticated, NotBlocked])
    def saved_me(self, request):
        qs = Project.objects.filter(saved_by=request.user).order_by("-created_at")
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    # -------- zip upload/download --------
    @action(detail=True, methods=["post"], url_path="upload-zip", permission_classes=[IsAuthenticated, NotBlocked])
    def upload_zip(self, request, pk=None):
        project = self.get_object()
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "file is required"}, status=400)
        count = project.ingest_zip(f)
        return Response({"ingested": count})

    @action(detail=True, methods=["get"], url_path="download.zip", permission_classes=[IsAuthenticated, NotBlocked])
    def download_zip(self, request, pk=None):
        project = self.get_object()
        data = project.as_zip_bytes()
        buf = io.BytesIO(data)
        buf.seek(0)
        return FileResponse(buf, as_attachment=True, filename=f"{project.name}.zip")

    # -------- invitations --------
    def _ensure_member_or_creator(self, project, user):
        if not (
            project.participants.filter(pk=getattr(user, "pk", None)).exists()
            or user == project.creator
            or getattr(user, "is_staff", False)
        ):
            raise PermissionDenied("Only participants, creator, or staff can modify annotations.")

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, NotBlocked])
    def invitations(self, request, pk=None):
        project = self.get_object()
        self._ensure_member_or_creator(project, request.user)
        ser = ProjectInvitationSerializer(project.invitations.order_by("-created_at"), many=True)
        return Response(ser.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked])
    def invite(self, request, pk=None):
        project = self.get_object()
        self._ensure_member_or_creator(project, request.user)
        invitee_id = request.data.get("invitee_id")
        if not invitee_id:
            return Response({"detail": "invitee_id required"}, status=400)
        invitee = get_object_or_404(User, pk=invitee_id)
        inv = ProjectInvitation.objects.create(
            project=project, inviter=request.user, invitee=invitee, message=request.data.get("message", "")
        )
        invitee.add_notification(f"You were invited to join '{project.name}' by {request.user}.")
        return Response(ProjectInvitationSerializer(inv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="invitations/(?P<inv_id>[^/.]+)/accept",
            permission_classes=[IsAuthenticated, NotBlocked])
    def accept_invitation(self, request, pk=None, inv_id=None):
        project = self.get_object()
        inv = get_object_or_404(ProjectInvitation, pk=inv_id, project=project)
        try:
            inv.accept(request.user)
            return Response({"detail": "Invitation accepted."})
        except (PermissionError, ValueError) as e:
            return Response({"detail": str(e)}, status=400)

    @action(detail=True, methods=["post"], url_path="invitations/(?P<inv_id>[^/.]+)/decline",
            permission_classes=[IsAuthenticated, NotBlocked])
    def decline_invitation(self, request, pk=None, inv_id=None):
        project = self.get_object()
        inv = get_object_or_404(ProjectInvitation, pk=inv_id, project=project)
        try:
            inv.decline(request.user)
            return Response({"detail": "Invitation declined."})
        except (PermissionError, ValueError) as e:
            return Response({"detail": str(e)}, status=400)

    @action(detail=True, methods=["post"], url_path="invitations/(?P<inv_id>[^/.]+)/revoke",
            permission_classes=[IsAuthenticated, NotBlocked])
    def revoke_invitation(self, request, pk=None, inv_id=None):
        project = self.get_object()
        inv = get_object_or_404(ProjectInvitation, pk=inv_id, project=project)  # <-- fix
        try:
            inv.revoke(request.user)
            return Response({"detail": "Invitation revoked."})
        except (PermissionError, ValueError) as e:
            return Response({"detail": str(e)}, status=400)

    def perform_destroy(self, instance):
        # send notifications to creator + participants
        instance.delete_with_notifications()

    def _ensure_member_or_creator(self, project, user):
        if not (
            project.participants.filter(pk=user.pk).exists()
            or user == project.creator
            or user.is_staff
        ):
            raise PermissionDenied("Only participants, creator, or staff can modify annotations.")

    @action(detail=True, methods=["get"], url_path="annotations", permission_classes=[NotBlocked])
    def get_annotations(self, request, pk=None):
        project = self.get_object()
        # Everyone can read annotations if they can read the project
        pf = project.files.filter(path=".graph/annotations.json").first()
        payload = []
        if pf and pf.content:
            try:
                payload = json.loads(pf.content)
            except json.JSONDecodeError:
                payload = []
        return Response({"notes": payload})

    @action(detail=True, methods=["post"], url_path="annotations", permission_classes=[IsAuthenticated, NotBlocked])
    def save_annotations(self, request, pk=None):
        project = self.get_object()
        self._ensure_member_or_creator(project, request.user)
        notes = request.data.get("notes", [])
        if not isinstance(notes, list):
            return Response({"detail": "notes must be a list"}, status=400)
        # optionally validate each note shape
        for n in notes:
            if not isinstance(n, dict):
                return Response({"detail": "each note must be an object"}, status=400)
        project.add_text_file(".graph/annotations.json", json.dumps(notes))
        return Response({"saved": len(notes)})

    def _ensure_member_or_creator(self, project, user):
        if not (
            project.participants.filter(pk=user.pk).exists()
            or user == project.creator
            or user.is_staff
        ):
            raise PermissionDenied("Only participants, creator, or staff can modify annotations.")

    @action(detail=True, methods=["get"], url_path="annotations", permission_classes=[NotBlocked])
    def get_annotations(self, request, pk=None):
        project = self.get_object()
        # Everyone can read annotations if they can read the project
        pf = project.files.filter(path=".graph/annotations.json").first()
        payload = []
        if pf and pf.content:
            try:
                payload = json.loads(pf.content)
            except json.JSONDecodeError:
                payload = []
        return Response({"notes": payload})

    @action(detail=True, methods=["post"], url_path="annotations", permission_classes=[IsAuthenticated, NotBlocked])
    def save_annotations(self, request, pk=None):
        project = self.get_object()
        self._ensure_member_or_creator(project, request.user)
        notes = request.data.get("notes", [])
        if not isinstance(notes, list):
            return Response({"detail": "notes must be a list"}, status=400)
        # optionally validate each note shape
        for n in notes:
            if not isinstance(n, dict):
                return Response({"detail": "each note must be an object"}, status=400)
        project.add_text_file(".graph/annotations.json", json.dumps(notes))
        return Response({"saved": len(notes)})

    @action(detail=True, methods=["get", "post"], url_path="annotations", permission_classes=[NotBlocked])
    def annotations(self, request, pk=None):
        """
        GET: return {"notes": [...]}
        POST: accept {"notes": [...]} and persist to .graph/annotations.json
        """
        project = self.get_object()

        # ---- GET ----
        if request.method == "GET":
            pf = project.files.filter(path=".graph/annotations.json").first()
            payload = []
            if pf and pf.content:
                try:
                    payload = json.loads(pf.content)
                except json.JSONDecodeError:
                    payload = []
            return Response({"notes": payload})

        # ---- POST ---- (must be authed + member/creator/staff)
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=401)
        self._ensure_member_or_creator(project, request.user)

        notes = request.data.get("notes", [])
        if not isinstance(notes, list):
            return Response({"detail": "notes must be a list"}, status=400)
        for n in notes:
            if not isinstance(n, dict):
                return Response({"detail": "each note must be an object"}, status=400)

        project.add_text_file(".graph/annotations.json", json.dumps(notes))
        return Response({"saved": len(notes)})

# ---------- Threads & Messages ----------
class ThreadViewSet(viewsets.ModelViewSet):
    queryset = Thread.objects.all().prefetch_related("participants", "messages")
    serializer_class = ThreadSerializer
    permission_classes = [NotBlocked, IsThreadParticipant]

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, NotBlocked, IsThreadParticipant])
    def add_message(self, request, pk=None):
        thread = self.get_object()
        content = request.data.get("content", "").strip()
        if not content:
            return Response({"detail": "content required"}, status=400)
        msg = thread.add_message(sender=request.user, content=content)
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="messages/(?P<message_id>[^/.]+)/like",
            permission_classes=[IsAuthenticated, NotBlocked, IsThreadParticipant])
    def like_message(self, request, pk=None, message_id=None):
        thread = self.get_object()
        msg = get_object_or_404(Message, pk=message_id, thread=thread)
        return Response({"detail": msg.like(request.user)})

    @action(detail=True, methods=["post"], url_path="messages/(?P<message_id>[^/.]+)/unlike",
            permission_classes=[IsAuthenticated, NotBlocked, IsThreadParticipant])
    def unlike_message(self, request, pk=None, message_id=None):
        thread = self.get_object()
        msg = get_object_or_404(Message, pk=message_id, thread=thread)
        return Response({"detail": msg.unlike(request.user)})

# ---------- Conversations & Private Messages ----------
class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [NotBlocked, IsAuthenticated]

    def get_permissions(self):
        if self.action in {"retrieve", "update", "partial_update", "destroy", "add_message", "like", "unlike"}:
            return [NotBlocked(), IsAuthenticated(), IsConversationParticipant()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], permission_classes=[NotBlocked, IsAuthenticated, IsConversationParticipant])
    def add_message(self, request, pk=None):
        conv = self.get_object()
        content = request.data.get("content", "").strip()
        if not content:
            return Response({"detail": "content required"}, status=400)
        pm = conv.add_message(sender=request.user, content=content)
        return Response(PrivateMessageSerializer(pm).data, status=201)

    @action(detail=True, methods=["post"], url_path="messages/(?P<pm_id>[^/.]+)/like",
            permission_classes=[NotBlocked, IsAuthenticated, IsConversationParticipant])
    def like(self, request, pk=None, pm_id=None):
        conv = self.get_object()
        pm = get_object_or_404(PrivateMessage, pk=pm_id, conversation=conv)
        return Response({"detail": pm.like(request.user)})

    @action(detail=True, methods=["post"], url_path="messages/(?P<pm_id>[^/.]+)/unlike",
            permission_classes=[NotBlocked, IsAuthenticated, IsConversationParticipant])
    def unlike(self, request, pk=None, pm_id=None):
        conv = self.get_object()
        pm = get_object_or_404(PrivateMessage, pk=pm_id, conversation=conv)
        return Response({"detail": pm.unlike(request.user)})