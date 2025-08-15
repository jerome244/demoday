from django.urls import path
from . import views

urlpatterns = [
    path("projects/<int:project_id>/upload-zip/", views.upload_zip, name="project-upload-zip"),
    path("projects/<int:project_id>/download.zip", views.download_project, name="project-download-zip"),
    path("threads/<int:thread_id>/messages/add/", views.thread_add_message, name="thread-add-message"),
]
