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


def _fake_zipball():
    """
    Build a GitHub-like zipball:
    top folder 'repo-abcdef/' containing a tiny web project.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/index.html", "<h1>hello</h1>\n")
        z.writestr("repo-abcdef/app.js", "console.log('hi')\n")
        z.writestr("repo-abcdef/README.md", "# readme\n")
    return buf.getvalue()


class _FakeResp:
    status_code = 200
    def __init__(self, data): self._data = data
    def iter_content(self, chunk_size=8192):
        # yield the whole file in one chunk (good enough for tests)
        yield self._data


@pytest.mark.asyncio
async def test_full_flow_github_import_edit_chat_download(monkeypatch, settings):
    # In-memory channel layer for deterministic WS
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

    # Monkeypatch GitHub zipball fetch
    data = _fake_zipball()
    def fake_get(url, headers=None, stream=True, timeout=30):
        return _FakeResp(data)
    monkeypatch.setattr("community.views.requests.get", fake_get)

    # Create users + project; add collaborator
    alice = await sync_to_async(User.objects.create_user)(
        username="alice", password="pw", name="Alice"
    )
    bob = await sync_to_async(User.objects.create_user)(
        username="bob", password="pw", name="Bob"
    )
    project = await sync_to_async(Project.objects.create)(
        name="web", creator=alice
    )
    await sync_to_async(project.participants.add)(bob)

    ac = AsyncClient()

    # --- 1) Import from GitHub ---
    import_url = reverse("community:project-import-github", args=[project.id])
    resp = await ac.post(
        import_url,
        data=json.dumps({
            "repo_url": "https://github.com/owner/repo",
            "ref": "main",
        }),
        content_type="application/json"
    )
    assert resp.status_code == 200
    assert resp.json()["imported_files"] >= 3

    # "graph is made": at least some files exist -> your parsing/graph step had material to build.
    file_names = set(await sync_to_async(list)(
        ProjectFile.objects.filter(project=project).values_list("path", flat=True)
    ))
    assert {"index.html", "app.js", "README.md"}.issubset(file_names)

    # --- 2) Modify "node popup text" -> simulate by editing README.md via ETag API ---
    # GET to read (and capture ETag)
    detail_url = reverse("community:project-file-detail", args=[project.id, "README.md"])
    resp = await ac.get(detail_url)
    assert resp.status_code == 200
    etag = resp.headers.get("ETag")
    new_md = "# readme\n\n**Edited from popup** ✅\n"

    # PUT with If-Match optimistic concurrency
    resp = await ac.put(
        detail_url,
        data=json.dumps({"content": new_md}),
        content_type="application/json",
        **({"HTTP_IF_MATCH": etag} if etag else {}),
    )
    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    pf = await sync_to_async(ProjectFile.objects.get)(project=project, path="README.md")
    assert pf.content == new_md

    # --- 3) Open WS for Bob, POST chat via HTTP as Alice, assert WS receive ---
    tok_bob = str(AccessToken.for_user(bob))
    ws = WebsocketCommunicator(
        application, f"/ws/chat/project/{project.id}/?token={tok_bob}"
    )
    ok, _ = await ws.connect()
    assert ok

    post_url = reverse("community:project-chat-post", args=[project.id])
    resp = await ac.post(
        post_url,
        data=json.dumps({"sender_id": alice.id, "content": "hello from github flow"}),
        content_type="application/json",
    )
    assert resp.status_code in (200, 201)
    msg = await ws.receive_json_from(timeout=3)
    assert msg["type"] == "message"
    assert msg["content"] == "hello from github flow"

    # NEW: ensure the shared chat thread exists with both users
    thread = await sync_to_async(Thread.objects.get)(title=f"project:{project.pk}:chat")
    member_ids = set(await sync_to_async(list)(
        thread.participants.values_list("id", flat=True)
    ))
    assert {alice.id, bob.id}.issubset(member_ids)

    # --- 4) Download ZIP and verify edited content persisted ---
    dl_url = reverse("community:project-download-zip", args=[project.id])
    resp = await ac.get(dl_url)
    assert resp.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    with z.open("README.md") as f:
        assert f.read().decode("utf-8") == new_md

    await ws.disconnect()
