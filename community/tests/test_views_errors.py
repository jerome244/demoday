import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

def test_upload_zip_missing_file_returns_400(client, project):
    url = reverse("project-upload-zip", args=[project.id])
    resp = client.post(url, {})  # no file
    assert resp.status_code == 400

def test_thread_add_message_missing_params_returns_400(client, thread):
    url = reverse("thread-add-message", args=[thread.id])
    # missing sender_id and content
    resp = client.post(url, {})
    assert resp.status_code == 400
