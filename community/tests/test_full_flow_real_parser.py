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
    Keep contents realistic so your real parser can work.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/index.html", "<script src='app.js'></script>\n")
        z.writestr("repo-abcdef/app.js", "function foo(){ bar(); }\nfunction bar(){}\nfoo();\n")
        z.writestr("repo-abcdef/README.md", "# readme\n")
    return buf.getvalue()


class _FakeResp:
    status_code = 200
    def __init__(self, data): self._data = data
    def iter_content(self, chunk_size=8192):
        yield self._data


@pytest.mark.asyncio
async def test_full_flow_real_parser(monkeypatch, settings):
    # Deterministic WS
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    # Fake GitHub download (only external piece we stub)
    data = _fake_zipball()
    def fake_get(url, headers=None, stream=True, timeout=30):
        return _FakeResp(data)
    monkeypatch.setattr("community.views.requests.get", fake_get)

    # Users + project
    alice = await sync_to_async(User.objects.create_user)(username="alice", password="pw", name="Alice")
    bob   = await sync_to_async(User.objects.create_user)(username="bob",   password="pw", name="Bob")
    proj  = await sync_to_async(Project.objects.create)(name="web", creator=alice)
    await sync_to_async(proj.participants.add)(bob)

    ac = AsyncClient()

    # 1) Import from GitHub (real view)
    import_url = reverse("community:project-import-github", args=[proj.id])
    resp = await ac.post(import_url, data=json.dumps({"repo_url":"https://github.com/owner/repo","ref":"main"}),
                         content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["imported_files"] >= 3

    # Files exist (real models)
    file_names = set(await sync_to_async(list)(
        ProjectFile.objects.filter(project=proj).values_list("path", flat=True)
    ))
    assert {"index.html", "app.js", "README.md"}.issubset(file_names)

    # 2) Graph via your REAL parser endpoint (no mocks)
    graph_url = reverse("community:project-graph", args=[proj.id])
    resp = await ac.get(graph_url)
    assert resp.status_code == 200
    graph = resp.json()["graph"]
    assert isinstance(graph, dict)
    assert isinstance(graph.get("nodes", []), list)
    assert isinstance(graph.get("edges", []), list)

    # 3) Edit a file, then re-graph
    detail_url = reverse("community:project-file-detail", args=[proj.id, "README.md"])
    r = await ac.get(detail_url)
    assert r.status_code == 200
    etag = r.headers.get("ETag")
    new_md = "# readme\n\nEdited via test ✅\n"
    r = await ac.put(detail_url, data=json.dumps({"content": new_md}), content_type="application/json",
                     **({"HTTP_IF_MATCH": etag} if etag else {}))
    assert r.status_code == 200
    pf = await sync_to_async(ProjectFile.objects.get)(project=proj, path="README.md")
    assert pf.content == new_md

    # Re-run graph after edit (still using real parser)
    resp = await ac.get(graph_url)
    assert resp.status_code == 200
    graph2 = resp.json()["graph"]
    assert isinstance(graph2, dict)
    assert "nodes" in graph2 and "edges" in graph2

    # 4) Realtime: open WS (real ASGI + consumer), post chat via HTTP, expect WS event
    tok_bob = str(AccessToken.for_user(bob))
    ws = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_bob}")
    ok, _ = await ws.connect(); assert ok

    post_url = reverse("community:project-chat-post", args=[proj.id])
    r = await ac.post(post_url, data=json.dumps({"sender_id": alice.id, "content": "hi from test"}),
                      content_type="application/json")
    assert r.status_code in (200, 201)
    msg = await ws.receive_json_from(timeout=3)
    assert msg["type"] == "message" and msg["content"] == "hi from test"

    # Thread exists with both users (real DB check)
    thread = await sync_to_async(Thread.objects.get)(title=f"project:{proj.pk}:chat")
    member_ids = set(await sync_to_async(list)(thread.participants.values_list("id", flat=True)))
    assert {alice.id, bob.id}.issubset(member_ids)

    # 5) Export: download ZIP reflects edited content (real export)
    dl_url = reverse("community:project-download-zip", args=[proj.id])
    r = await ac.get(dl_url)
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open("README.md") as f:
        assert f.read().decode("utf-8") == new_md

    await ws.disconnect()
