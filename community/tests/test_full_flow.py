import io
import json
import zipfile
import pytest

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import AsyncClient
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken

from flowchart.asgi import application
from community.models import Project, User, ProjectFile, Thread

pytestmark = pytest.mark.django_db(transaction=True)

@pytest.mark.asyncio
async def test_full_flow_upload_edit_chat_download(settings):
    # Use in-memory channel layer for deterministic tests
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

    # --- Create users & project (ORM is sync => wrap) ---
    alice = await sync_to_async(User.objects.create_user)(
        username="alice", password="pw", name="Alice"
    )
    bob = await sync_to_async(User.objects.create_user)(
        username="bob", password="pw", name="Bob"
    )
    project = await sync_to_async(Project.objects.create)(
        name="demo", creator=alice
    )
    await sync_to_async(project.participants.add)(bob)

    # --- Build a tiny zip in memory ---
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app.py", "print('hello')\n")
        zf.writestr("README.md", "# Readme\n")
    zbuf.seek(0)

    # Use Django AsyncClient
    ac = AsyncClient()

    # --- Upload zip ---
    upload_url = reverse("community:project-upload-zip", args=[project.id])
    resp = await ac.post(upload_url, {"file": zbuf}, format="multipart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ingested"] >= 2

    # Verify files exist in DB
    file_count = await sync_to_async(ProjectFile.objects.filter(project=project).count)()
    assert file_count >= 2

    # --- Read a file and capture ETag ---
    detail_url = reverse("community:project-file-detail", args=[project.id, "app.py"])
    resp = await ac.get(detail_url)
    assert resp.status_code == 200
    etag = resp.headers.get("ETag")
    original = resp.json()
    assert original["content"] == "print('hello')\n"

    # --- Update file with If-Match optimistic concurrency ---
    new_content = "print('hi from test')\n"
    resp = await ac.put(
        detail_url,
        data=json.dumps({"content": new_content}),
        content_type="application/json",
        **({"HTTP_IF_MATCH": etag} if etag else {}),
    )
    assert resp.status_code == 200
    assert resp.json()["saved"] is True

    # Ensure DB reflects new content
    pf = await sync_to_async(ProjectFile.objects.get)(project=project, path="app.py")
    assert pf.content == new_content

    # --- Open WS as Bob (JWT query param) ---
    token = str(AccessToken.for_user(bob))
    communicator = WebsocketCommunicator(
        application, f"/ws/chat/project/{project.id}/?token={token}"
    )
    connected, _ = await communicator.connect()
    assert connected

    # --- Post a chat message via HTTP as Alice, expect WS broadcast to Bob ---
    post_url = reverse("community:project-chat-post", args=[project.id])
    resp = await ac.post(
        post_url,
        data=json.dumps({"sender_id": alice.id, "content": "hello via http"}),
        content_type="application/json",
    )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["content"] == "hello via http"

    ws_msg = await communicator.receive_json_from(timeout=3)
    assert ws_msg["type"] == "message"
    assert ws_msg["content"] == "hello via http"
    assert ws_msg["sender"] in ("Alice", "alice")

    # --- Thread membership includes both users ---
    thread = await sync_to_async(Thread.objects.get)(title=f"project:{project.pk}:chat")
    member_ids = set(await sync_to_async(list)(thread.participants.values_list("id", flat=True)))
    assert {alice.id, bob.id}.issubset(member_ids)

    # --- Download the project zip and verify modified file is inside ---
    dl_url = reverse("community:project-download-zip", args=[project.id])
    resp = await ac.get(dl_url)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    with z.open("app.py") as f:
        assert f.read().decode("utf-8") == new_content

    await communicator.disconnect()
