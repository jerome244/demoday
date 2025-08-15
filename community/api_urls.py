from rest_framework.routers import DefaultRouter
from .api import UserViewSet, ProjectViewSet, ThreadViewSet, ConversationViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")
router.register(r"projects", ProjectViewSet, basename="projects")
router.register(r"threads", ThreadViewSet, basename="threads")
router.register(r"conversations", ConversationViewSet, basename="conversations")

urlpatterns = router.urls