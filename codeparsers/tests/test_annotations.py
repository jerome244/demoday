import json
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

def _rand(n=6):
    import random, string
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def make_user(username: str, email: str, password: str) -> int:
    c = APIClient()
    payload = {"username": username, "email": email, "password": password, "name": username.title()}
    r = c.post("/api/community/v2/users/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code in (200, 201), r.content
    return r.json()["id"]

def token(username, password) -> str:
    c = APIClient()
    r = c.post("/api/auth/token/", {"username": username, "password": password}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["access"]

def authed(token: str) -> APIClient:
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}"); return c

def test_annotations_roundtrip():
    # creator
    u, p = f"user_{_rand()}", "Passw0rd!123"
    uid = make_user(u, f"{u}@ex.com", p)
    t = token(u, p)
    c = authed(t)

    # create project
    name = f"proj-{_rand()}"
    r = c.post("/api/community/v2/projects/", {"name": name, "description": "", "creator": uid}, format="json")
    assert r.status_code in (200, 201), r.content
    pid = r.json()["id"]

    # save 2 notes
    notes = [
        {"id": "note-1", "label": "todo", "position": {"x": 100, "y": 150}},
        {"id": "note-2", "label": "fix me", "position": {"x": 300, "y": 250}},
    ]
    r = c.post(f"/api/community/v2/projects/{pid}/annotations/", {"notes": notes}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["saved"] == 2

    # load notes back
    r = c.get(f"/api/community/v2/projects/{pid}/annotations/")
    assert r.status_code == 200
    got = r.json()["notes"]
    # compare by id/label
    s = { (n["id"], n["label"]) for n in got }
    assert ("note-1", "todo") in s and ("note-2", "fix me") in s
