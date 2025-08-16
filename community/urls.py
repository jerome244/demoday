# community/urls.py
from django.urls import path, re_path
from . import views

app_name = "community"

urlpatterns = [
    # ZIP upload/download
    path("projects/<int:project_id>/upload-zip/", views.upload_zip, name="project-upload-zip"),
    path("projects/<int:project_id>/download.zip", views.download_project, name="project-download-zip"),

    # Files
    path("projects/<int:project_id>/files/bulk/", views.project_files_bulk, name="project-files-bulk"),
    path("projects/<int:project_id>/files/tree/", views.project_file_tree, name="project-file-tree"),
    re_path(r"^projects/(?P<project_id>\d+)/files/(?P<path>.+)/$", views.project_file_detail, name="project-file-detail"),

    # Graph & summary
    path("projects/<int:project_id>/graph/", views.project_graph, name="project-graph"),
    path("projects/<int:project_id>/summary", views.project_summary, name="project-summary"),

    # GitHub import
    path("projects/<int:project_id>/import/github/", views.project_import_github, name="project-import-github"),

    # Threads (direct thread API used in error tests)
    path("threads/<int:thread_id>/messages/add/", views.thread_add_message, name="thread-add-message"),

    # Project-wide chat
    path("projects/<int:project_id>/chat/", views.project_chat_info, name="project-chat-info"),
    path("projects/<int:project_id>/chat/messages/", views.project_chat_messages, name="project-chat-messages"),
    path("projects/<int:project_id>/chat/messages/add/", views.project_chat_post, name="project-chat-post"),
]
