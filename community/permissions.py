from rest_framework.permissions import BasePermission, SAFE_METHODS

class NotBlocked(BasePermission):
    """Deny all requests from blocked users."""
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return True
        return not getattr(u, "blocked", False)

class IsCreatorOrReadOnly(BasePermission):
    """Write access only to the object's creator or staff; read allowed for everyone by default."""
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        creator = getattr(obj, "creator", None)
        return (creator == request.user) or request.user.is_staff

class IsThreadParticipant(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return obj.participants.filter(pk=getattr(request.user, 'pk', None)).exists() or request.user.is_staff
        return obj.participants.filter(pk=getattr(request.user, 'pk', None)).exists() or request.user.is_staff

class IsConversationParticipant(BasePermission):
    def has_object_permission(self, request, view, obj):
        uid = getattr(request.user, 'pk', None)
        return uid in (obj.user1_id, obj.user2_id) or request.user.is_staff