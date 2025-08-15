from django.urls import path
from . import views
from django.urls import path, include

urlpatterns = [
    # optional helpers if you use the views I shared previously:
    path("projects/<int:project_id>/upload-zip/", views.upload_zip, name="project-upload-zip"),
    path("projects/<int:project_id>/download.zip", views.download_project, name="project-download-zip"),
    path("threads/<int:thread_id>/messages/add/", views.thread_add_message, name="thread-add-message"),
    path("api/community/v2/", include("community.api_urls")),
]
