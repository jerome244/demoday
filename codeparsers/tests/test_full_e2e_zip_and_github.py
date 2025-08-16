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
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"Did not receive any of {want} before timeout")
        msg = await comm.receive_json_from(timeout=remaining)
        if msg.get("type") in want:
            return msg
        # drain other events (presence.join/roster/etc.) and continue


# ------------------------- ZIP FLOW -------------------------

@pytest.mark.asyncio
async def test_e2e_zip_upload_parse_match_save_chat_presence_download(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    # Users + project
    alice = await sync_to_async(User.objects.create_user)(username="alice", password="pw")
    bob   = await sync_to_async(User.objects.create_user)(username="bob",   password="pw")
    proj  = await sync_to_async(Project.objects.create)(name="zipproj", creator=alice)
    await sync_to_async(proj.participants.add)(bob)

    # ZIP contents (no top folder for upload_zip)
    html = '<link rel="stylesheet" href="styles.css"><div class="test btn" id="hero">hi</div>\n'
    css  = '.test { color:red; } .btn:hover { cursor:pointer; } #hero { margin:0; }\n'
    js   = 'function foo(){ bar(); } function bar(){} foo();\n'
    zbytes = _build_zip({
        "index.html": html,
        "styles.css": css,
        "app.js": js,
    })

    ac = AsyncClient()

    # Upload zip
    up_url = reverse("community:project-upload-zip", args=[proj.id])
    resp = await ac.post(up_url, {"file": io.BytesIO(zbytes)}, format="multipart")
    assert resp.status_code == 200
    assert resp.json()["ingested"] >= 3

    # Files exist
    names = set(await sync_to_async(list)(
        ProjectFile.objects.filter(project=proj).values_list("path", flat=True)
    ))
    assert {"index.html", "styles.css", "app.js"}.issubset(names)

    # ----- Parse & match HTML <-> CSS using your real parser -----
    html_file = await sync_to_async(ProjectFile.objects.get)(project=proj, path="index.html")
    css_file  = await sync_to_async(ProjectFile.objects.get)(project=proj, path="styles.css")

    html_rel = parse_code("html", "index.html", html_file.content, {"styles.css": css_file.content})
    matched = html_rel["matched_css"]
    assert {".test", ".btn", "#hero"}.issubset(set(matched.keys()))

    # ----- Edit & save with ETag -----
    detail_url = reverse("community:project-file-detail", args=[proj.id, "index.html"])
    r = await ac.get(detail_url); assert r.status_code == 200
    etag = r.headers.get("ETag")
    new_html = html.replace("hi", "hello edited")
    r = await ac.put(detail_url, data=json.dumps({"content": new_html}),
                     content_type="application/json", **({"HTTP_IF_MATCH": etag} if etag else {}))
    assert r.status_code == 200 and r.json()["saved"] is True
    updated = await sync_to_async(ProjectFile.objects.get)(project=proj, path="index.html")
    assert updated.content == new_html

    # ----- Realtime: presence + cursor + chat -----
    tok_alice = str(AccessToken.for_user(alice))
    tok_bob   = str(AccessToken.for_user(bob))

    wa = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_alice}")
    wb = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_bob}")
    ok, _ = await wa.connect(); assert ok
    ok, _ = await wb.connect(); assert ok

    # presence
    await wa.send_json_to({"type": "presence.hello"})
    await wb.send_json_to({"type": "presence.hello"})
    _ = await recv_until(wa, {"presence.roster"})
    _ = await recv_until(wb, {"presence.roster"})

    # cursor from Alice -> Bob sees update
    await wa.send_json_to({"type": "cursor.move", "x": 0.33, "y": 0.66})
    msg = await recv_until(wb, {"cursor.update"})
    assert 0 <= msg["x"] <= 1 and 0 <= msg["y"] <= 1

    # chat via HTTP (Alice) -> Bob receives on WS
    post_url = reverse("community:project-chat-post", args=[proj.id])
    r = await ac.post(post_url, data=json.dumps({"sender_id": alice.id, "content": "zip hello"}),
                      content_type="application/json")
    assert r.status_code in (200, 201)
    msg = await recv_until(wb, {"message"})
    assert msg["content"] == "zip hello"

    # ----- Download zip & verify persisted edit -----
    dl_url = reverse("community:project-download-zip", args=[proj.id])
    r = await ac.get(dl_url); assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open("index.html") as f:
        assert f.read().decode("utf-8") == new_html

    await wa.disconnect(); await wb.disconnect()


# ------------------------- GITHUB FLOW -------------------------

class _FakeResp:
    status_code = 200
    def __init__(self, data): self._data = data
    def iter_content(self, chunk_size=8192):
        yield self._data

@pytest.mark.asyncio
async def test_e2e_github_import_parse_match_save_chat_presence_download(monkeypatch, settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    # Build a GitHub-like zipball (top-level folder)
    html = '<link rel="stylesheet" href="styles.css"><div class="test btn" id="hero">hey</div>\n'
    css  = '.test{color:red} .btn:hover{cursor:pointer} #hero{margin:0}\n'
    js   = 'function f(){g()} function g(){} f();\n'
    gh_bytes = _build_zip({
        "repo-abcdef/index.html": html,
        "repo-abcdef/styles.css": css,
        "repo-abcdef/app.js": js,
    })
    monkeypatch.setattr("community.views.requests.get", lambda *a, **k: _FakeResp(gh_bytes))

    # Users + project
    alice = await sync_to_async(User.objects.create_user)(username="alice2", password="pw")
    bob   = await sync_to_async(User.objects.create_user)(username="bob2",   password="pw")
    proj  = await sync_to_async(Project.objects.create)(name="ghproj", creator=alice)
    await sync_to_async(proj.participants.add)(bob)

    ac = AsyncClient()

    # Import from GitHub (view strips top folder)
    imp_url = reverse("community:project-import-github", args=[proj.id])
    r = await ac.post(imp_url, data=json.dumps({"repo_url": "https://github.com/owner/repo", "ref":"main"}),
                      content_type="application/json")
    assert r.status_code == 200
    names = set(await sync_to_async(list)(
        ProjectFile.objects.filter(project=proj).values_list("path", flat=True)
    ))
    assert {"index.html", "styles.css", "app.js"}.issubset(names)

    # Parse & match (real parsers)
    html_file = await sync_to_async(ProjectFile.objects.get)(project=proj, path="index.html")
    css_file  = await sync_to_async(ProjectFile.objects.get)(project=proj, path="styles.css")
    html_rel = parse_code("html", "index.html", html_file.content, {"styles.css": css_file.content})
    assert {".test", ".btn", "#hero"}.issubset(set(html_rel["matched_css"].keys()))

    # Edit + save
    detail_url = reverse("community:project-file-detail", args=[proj.id, "index.html"])
    r = await ac.get(detail_url); assert r.status_code == 200
    etag = r.headers.get("ETag")
    new_html = html.replace("hey", "hey edited")
    r = await ac.put(detail_url, data=json.dumps({"content": new_html}),
                     content_type="application/json", **({"HTTP_IF_MATCH": etag} if etag else {}))
    assert r.status_code == 200

    # Realtime: presence + cursor + chat
    tok_bob = str(AccessToken.for_user(bob))
    wa = WebsocketCommunicator(application, f"/ws/chat/project/{proj.id}/?token={tok_bob}")
    ok, _ = await wa.connect(); assert ok

    # announce presence from single client so at least roster arrives (could be empty)
    await wa.send_json_to({"type": "presence.hello"})
    _ = await recv_until(wa, {"presence.roster"})

    # Post chat via HTTP (Alice) -> WS sees message
    post_url = reverse("community:project-chat-post", args=[proj.id])
    r = await ac.post(post_url, data=json.dumps({"sender_id": alice.id, "content": "gh hello"}),
                      content_type="application/json")
    assert r.status_code in (200, 201)
    msg = await recv_until(wa, {"message"})
    assert msg["content"] == "gh hello"

    # Download zip & verify edited content
    dl_url = reverse("community:project-download-zip", args=[proj.id])
    r = await ac.get(dl_url); assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open("index.html") as f:
        assert f.read().decode("utf-8") == new_html

    await wa.disconnect()
