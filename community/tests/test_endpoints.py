import io
import zipfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
import pytest
from community.models import Message

pytestmark = pytest.mark.django_db

def make_zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buf.seek(0)
    return buf.read()

def test_upload_zip_ingests_files(client, project):
    data = make_zip_bytes({"a.txt": "hi", "src/b.py": "print(1)"})
    uploaded = SimpleUploadedFile("demo.zip", data, content_type="application/zip")
    url = reverse("project-upload-zip", args=[project.id])
    resp = client.post(url, {"file": uploaded})
    assert resp.status_code == 200
    assert resp.json()["ingested"] == 2
    assert project.files.count() == 2

def test_download_project_returns_zip(client, project):
    # Seed a couple files
    project.add_text_file("README.md", "# readme")
    project.add_text_file("src/app.py", "print('ok')")
    url = reverse("project-download-zip", args=[project.id])
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/zip"
    # Inspect zip contents
    zdata = io.BytesIO(resp.content)
    with zipfile.ZipFile(zdata) as zf:
        names = set(zf.namelist())
    assert {"README.md", "src/app.py"} <= names

def test_thread_add_message_endpoint_notifies_others(client, thread, user, other_user):
    url = reverse("thread-add-message", args=[thread.id])
    resp = client.post(url, {"sender_id": user.id, "content": "Hello world"})
    assert resp.status_code == 200
    # Message created
    assert Message.objects.filter(thread=thread, sender=user, content="Hello world").exists()
    # Notification sent to the other participant
    note = other_user.notifications.latest("created_at")
    assert "Hello world" in note.message and thread.title in note.message
