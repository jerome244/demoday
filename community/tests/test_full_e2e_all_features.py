import io
import json
import zipfile
import asyncio
import pytest

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import AsyncClient
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken

from flowchart.asgi import application
from community.models import Project, User, ProjectFile
from codeparsers.parsers import parse_code


pytestmark = pytest.mark.django_db(transaction=True)


# ------------------------- helpers -------------------------

def _build_zip(files: dict[str, str]) -> bytes:
    """Create an in-memory zip from {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr(path, content)
    return buf.getvalue()

async def recv_until(comm: WebsocketCommunicator, want: set[str], timeout: float = 3.0):
    """Receive WS frames until one of `want` types arrives (or timeout)."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last = None
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"Did not receive any of {want}; last={last}")
        msg = await comm.receive_json_from(timeout=remaining)
        last = msg
        t = msg.get("type")
        if t in want:
            return msg
        # Ignore other noise (presence.join, typing, etc.) and keep waiting


# ------------------------- ZIP FLOW -------------------------

@pytest.mark.asyncio
async def test_full_e2e_zip_flow(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    # Users + project
    alice = await sync_to_async(User.objects.create_user)(username="alice_zip", password="pw")
    bob   = await sync_to_async(User.objects.create_user)(username="bob_zip",   password="pw")
    proj  = await sync_to_async(Project.objects.create)(name="zipproj", creator=alice)
    await sync_to_async(proj.participants.add)(bob)

    # ZIP contents (with nested dirs to simulate a small tree)
    html = '<link rel="stylesheet" href="assets/styles.css"><div class="test btn" id="hero">hi</div>\n'
    css  = '.test { color:red; } .btn:hover { cursor:pointer; } #hero { margin:0; }\n'
    js   = 'function foo(){ bar(); } function bar(){} foo();\n'
    py_bad = 'def oops(:\n    pass\n'  # trigger lint error in preview
    zbytes = _build_zip({
        "index.html": html,
        "assets/styles.css": css,
        "static/app.js": js,
        "scripts/broken.py": py_bad,
    })

    ac = AsyncClient()

    # Upload zip
    up_url = reverse("community:project-upload-zip", args=[proj.id])
    resp = await ac.post(up_url, {"file": io.BytesIO(zbytes)}, format="multipart")
    assert resp.status_code == 200
    assert resp.json()["ingested"] >= 4

    # Files exist (tree-like structure: nested paths)
    names = set(await sync_to_async(list)(
        ProjectFile.objects.filter(project=proj).values_list("path", flat=True)
    ))
    assert {"index.html", "assets/styles.css", "static/app.js", "scripts/broken.py"}.issubset(names)

    # ----- Parse & match HTML <-> CSS using your real parser -----
    html_file = await sync_to_async(ProjectFile.objects.get)(project=proj, path="index.html")
    css_file  = await sync_to_async(ProjectFile.objects.get)(project=proj, path="assets/styles.css")
    html_rel = parse_code("html", "index.html", html_file.content, {"assets/styles.css": css_file.content})
    assert {".test", ".btn", "#hero"}.issubset(set(html_rel["matched_css"].keys()))

    # ----- Graph API (shape check; nodes/edges present) -----
    graph_url = reverse("community:project-graph", args=[proj.id])
    r = await ac.get(graph_url)
    assert r.status_code == 200
    graph = r.json()["graph"]
    assert isinstance(graph, dict)
    assert "nodes" in graph and "edges" in graph

    # ----- Popup "Format + Lint" PREVIEW on broken.py (should report diagnostics, do not save) -----
    detail_py = reverse("community:project-file-detail", args=[proj.id, "scripts/broken.py"])
    r = await ac.put(detail_py + "?preview=1&format=1&lint=1",
                     data=json.dumps({"content": py_bad}), content_type="application/json")
    assert r.status_code == 200
    data = r.json()
    assert data["preview"] is True
    assert isinstance(data.get("diagnostics"), list) and len(data["diagnostics"]) >= 1
    # Original content unchanged on GET
    r0 = await ac.get(detail_py)
    assert r0.status_code == 200
    assert r0.json()["content"] == py_bad  # still broken

    # ----- Fix code, SAVE with format+lint (diagnostics should be empty now) -----
    py_fixed = "def ok():\n    return 42\n"
    r = await ac.put(detail_py + "?format=1&lint=1",
                     data=json.dumps({"content": py_fixed}), content_type="application/json")
    assert r.status_code == 200
    assert r.json()["saved"] is True
    assert r.json().get("diagnostics") == []

    # ----- Realtime: presence + cursor + chat -----
    tok_alice = str(AccessToken.for_user(alice))
    tok_bob   = str(AccessToken.for_user(bob))
    wa = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_alice}")
    wb = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_bob}")
    ok, _ = await wa.connect(); assert ok
    ok, _ = await wb.connect(); assert ok

    # presence/roster
    await wa.send_json_to({"type": "presence.hello"})
    await wb.send_json_to({"type": "presence.hello"})
    _ = await recv_until(wa, {"presence.roster"})
    _ = await recv_until(wb, {"presence.roster"})

    # cursor (alice -> bob)
    await wa.send_json_to({"type": "cursor.move", "x": 0.2, "y": 0.8})
    msg = await recv_until(wb, {"cursor.update"})
    assert 0 <= msg["x"] <= 1 and 0 <= msg["y"] <= 1

    # chat over HTTP -> fan-out to WS
    post_url = reverse("community:project-chat-post", args=[proj.id])
    r = await ac.post(post_url, data=json.dumps({"sender_id": alice.id, "content": "zip: hello team!"}),
                      content_type="application/json")
    assert r.status_code in (200, 201)
    msg = await recv_until(wb, {"message"})
    assert msg["content"] == "zip: hello team!"

    # ----- Download zip & verify persisted edit on Python file -----
    dl_url = reverse("community:project-download-zip", args=[proj.id])
    r = await ac.get(dl_url); assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open("scripts/broken.py") as f:
        assert f.read().decode("utf-8") == (py_fixed.rstrip("\n") + "\n")

    await wa.disconnect(); await wb.disconnect()


# ------------------------- GITHUB FLOW -------------------------

class _FakeResp:
    status_code = 200
    def __init__(self, data): self._data = data
    def iter_content(self, chunk_size=8192):
        yield self._data

@pytest.mark.asyncio
async def test_full_e2e_github_flow(settings, monkeypatch):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    # Build a GitHub-like zipball (top-level folder)
    html = '<link rel="stylesheet" href="styles.css"><div class="test btn" id="hero">hey</div>\n'
    css  = '.test{color:red} .btn:hover{cursor:pointer} #hero{margin:0}\n'
    js   = 'function f(){g()} function g(){} f();\n'
    py   = 'def api():\n    return "ok"\n'
    gh_bytes = _build_zip({
        "repo-abcdef/index.html": html,
        "repo-abcdef/styles.css": css,
        "repo-abcdef/app.js": js,
        "repo-abcdef/server/api.py": py,
    })
    monkeypatch.setattr("community.views.requests.get", lambda *a, **k: _FakeResp(gh_bytes))

    # Users + project
    alice = await sync_to_async(User.objects.create_user)(username="alice_gh", password="pw")
    bob   = await sync_to_async(User.objects.create_user)(username="bob_gh",   password="pw")
    proj  = await sync_to_async(Project.objects.create)(name="ghproj", creator=alice)
    await sync_to_async(proj.participants.add)(bob)

    ac = AsyncClient()

    # Import from GitHub (view strips the top folder)
    imp_url = reverse("community:project-import-github", args=[proj.id])
    r = await ac.post(imp_url, data=json.dumps({"repo_url": "https://github.com/owner/repo", "ref":"main"}),
                      content_type="application/json")
    assert r.status_code == 200

    names = set(await sync_to_async(list)(
        ProjectFile.objects.filter(project=proj).values_list("path", flat=True)
    ))
    assert {"index.html", "styles.css", "app.js", "server/api.py"}.issubset(names)

    # Parse & match (real parsers)
    html_file = await sync_to_async(ProjectFile.objects.get)(project=proj, path="index.html")
    css_file  = await sync_to_async(ProjectFile.objects.get)(project=proj, path="styles.css")
    html_rel = parse_code("html", "index.html", html_file.content, {"styles.css": css_file.content})
    assert {".test", ".btn", "#hero"}.issubset(set(html_rel["matched_css"].keys()))

    # Graph API
    graph_url = reverse("community:project-graph", args=[proj.id])
    r = await ac.get(graph_url)
    assert r.status_code == 200
    graph = r.json()["graph"]
    assert "nodes" in graph and "edges" in graph

    # Popup preview format+lint on API file
    detail_api = reverse("community:project-file-detail", args=[proj.id, "server/api.py"])
    r = await ac.put(detail_api + "?preview=1&format=1&lint=1",
                     data=json.dumps({"content": py}), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("preview") is True
    assert isinstance(r.json().get("diagnostics"), list)

    # Presence + chat (single WS ok)
    tok_bob = str(AccessToken.for_user(bob))
    ws = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_bob}")
    ok, _ = await ws.connect(); assert ok
    await ws.send_json_to({"type": "presence.hello"})
    _ = await recv_until(ws, {"presence.roster"})

    post_url = reverse("community:project-chat-post", args=[proj.id])
    r = await ac.post(post_url, data=json.dumps({"sender_id": alice.id, "content": "gh: hello!"}),
                      content_type="application/json")
    assert r.status_code in (200, 201)
    msg = await recv_until(ws, {"message"})
    assert msg["content"] == "gh: hello!"

    # Download zip reflects current state
    dl_url = reverse("community:project-download-zip", args=[proj.id])
    r = await ac.get(dl_url); assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert "server/api.py" in z.namelist()

    await ws.disconnect()
