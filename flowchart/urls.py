# flowchart/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# add this import
from community import views as community_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # ---- Global names used by tests (unnamespaced) ----
    path(
        "api/community/projects/<int:project_id>/upload-zip/",
        community_views.upload_zip,
        name="project-upload-zip",
    ),
    path(
        "api/community/projects/<int:project_id>/download.zip",
        community_views.download_project,
        name="project-download-zip",
    ),
    path(
        "api/community/threads/<int:thread_id>/messages/add/",
        community_views.thread_add_message,
        name="thread-add-message",
    ),

    # ---- Namespaced include for the rest of the API ----
    path("api/community/", include(("community.urls", "community"), namespace="community")),

    path("api/code/", include("codeparsers.urls")),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
