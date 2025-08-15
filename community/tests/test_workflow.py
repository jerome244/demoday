import io
import json
import zipfile
import random
import string
from typing import Dict

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile

pytestmark = pytest.mark.django_db


def _rand(suffix_len=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=suffix_len))


def make_zip_bytes(files: Dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr(path, content)
    buf.seek(0)
    return buf.read()


def auth_client(token: str) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def get_token(username: str, password: str) -> str:
    c = APIClient()
    r = c.post("/api/auth/token/", {"username": username, "password": password}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["access"]


def create_user_via_api(username: str, email: str, password: str) -> int:
    c = APIClient()
    payload = {"username": username, "email": email, "password": password, "name": username.title()}
    r = c.post("/api/community/v2/users/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code in (201, 200), r.content
    return r.json()["id"]


def test_full_global_workflow():
    # --- 1) Create two users via API ---
    u1 = f"user_{_rand()}"
    u2 = f"user_{_rand()}"
    p1 = "Passw0rd!123"
    p2 = "Passw0rd!456"
    user1_id = create_user_via_api(u1, f"{u1}@example.com", p1)
    user2_id = create_user_via_api(u2, f"{u2}@example.com", p2)

    # --- 2) Auth (JWT) ---
    t1 = get_token(u1, p1)
    t2 = get_token(u2, p2)
    c1 = auth_client(t1)
    c2 = auth_client(t2)

    # --- 3) Create a project as user1 (include creator) ---
    project_name = f"proj-{_rand()}"
    r = c1.post(
        "/api/community/v2/projects/",
        {"name": project_name, "description": "e2e test", "creator": user1_id},
        format="json",
    )
    assert r.status_code in (201, 200), r.content
    project = r.json()
    project_id = project["id"]

    # --- 4) Upload a ZIP of source files into the project ---
    files = {
        "a.py": "def greet(name):\n    return f'hi {name}'\n",
        "b.py": "from a import greet\nprint(greet('Bob'))\n",
        "README.md": "# sample\n",
    }
    zip_bytes = make_zip_bytes(files)
    upload = SimpleUploadedFile("sample.zip", zip_bytes, content_type="application/zip")
    r = c1.post(f"/api/community/v2/projects/{project_id}/upload-zip/", {"file": upload}, format="multipart")
    assert r.status_code in (200, 201), r.content
    uploaded = r.json()
    assert uploaded.get("ingested", 0) >= 2  # a.py + b.py at least

    # --- 5) Parse the ZIP with codeparsers to check declared-vs-called matches ---
    upload2 = SimpleUploadedFile("sample.zip", zip_bytes, content_type="application/zip")
    r = c1.post("/api/code/parse-zip/", {"file": upload2}, format="multipart")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "global" in data and "files" in data, data
    g = data["global"]
    defined_names = [d.get("name") or d.get("function") for d in g.get("defined", [])]
    assert "greet" in defined_names
    called_map = g.get("called", {})
    metrics = g.get("metrics", {})
    has_greet_called = False
    if isinstance(called_map, dict):
        for k, v in called_map.items():
            if "greet" in str(k) or any("greet" in str(it) for it in (v if isinstance(v, list) else [v])):
                has_greet_called = True
                break
    if not has_greet_called and isinstance(metrics, dict):
        has_greet_called = any((m or {}).get("num_calls", 0) > 0 for m in metrics.values())
    assert has_greet_called, f"Expected 'greet' call tracked in {g}"

    # --- 6) Save (bookmark) the project ---
    r = c1.post(f"/api/community/v2/projects/{project_id}/save/")
    assert r.status_code in (200, 201), r.content
    # Verify it's listed under saved/me (note trailing slash)
    r = c1.get("/api/community/v2/projects/saved/me/")
    assert r.status_code == 200, r.content
    saved_ids = [p["id"] for p in r.json().get("results", r.json())]
    assert project_id in saved_ids

    # --- 7) Share with other user via invitation ---
    r = c1.post(f"/api/community/v2/projects/{project_id}/invite/", {"invitee_id": user2_id}, format="json")
    assert r.status_code == 201, r.content
    inv = r.json()
    inv_id = inv["id"]

    # Other user should receive a notification
    U = get_user_model()
    other = U.objects.get(pk=user2_id)
    latest = other.notifications.latest("created_at")
    assert "invited" in latest.message.lower()

    # --- 8) Other user accepts the invitation (note trailing slash) ---
    r = c2.post(f"/api/community/v2/projects/{project_id}/invitations/{inv_id}/accept/")
    assert r.status_code == 200, r.content

    # Project participants should now include other user
    r = c1.get(f"/api/community/v2/projects/{project_id}/")
    assert r.status_code == 200, r.content
    participants = set(r.json().get("participants", []))
    assert user2_id in participants

    # Inviter should see an "accepted" or "added" style notification
    me = U.objects.get(pk=user1_id)
    msgs = list(me.notifications.order_by("-created_at").values_list("message", flat=True))
    assert any("accepted" in m.lower() or "added to the project" in m.lower() for m in msgs)

