import io
import json
import zipfile
from typing import Dict

import pytest
from django.contrib.auth import get_user_model
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


def get_token(username: str, password: str) -> str:
    c = APIClient()
    r = c.post("/api/auth/token/", {"username": username, "password": password}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["access"]


def auth_client(token: str) -> APIClient:
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def test_like_dislike_notifies_owner():
    # --- create two users ---
    u1, p1 = f"user_{_rand()}", "Passw0rd!123"
    u2, p2 = f"user_{_rand()}", "Passw0rd!456"
    owner_id = make_user(u1, f"{u1}@ex.com", p1)
    other_id = make_user(u2, f"{u2}@ex.com", p2)

    t1 = get_token(u1, p1)
    t2 = get_token(u2, p2)
    c1 = auth_client(t1)  # owner client
    c2 = auth_client(t2)  # other user client

    # --- owner creates a project ---
    proj_name = f"proj-{_rand()}"
    r = c1.post(
        "/api/community/v2/projects/",
        {"name": proj_name, "description": "", "creator": owner_id},
        format="json",
    )
    assert r.status_code in (200, 201), r.content
    project_id = r.json()["id"]

    # --- other user can view the owner's project (public read) ---
    r = c2.get(f"/api/community/v2/projects/{project_id}/")
    assert r.status_code == 200, r.content

    # --- like by other user triggers owner notification ---
    U = get_user_model()
    owner = U.objects.get(pk=owner_id)
    before = owner.notifications.count()

    r = c2.post(f"/api/community/v2/projects/{project_id}/like/")
    assert r.status_code in (200, 201), r.content

    owner.refresh_from_db()
    assert owner.notifications.count() == before + 1
    msg = owner.notifications.latest("created_at").message.lower()
    assert "liked your project" in msg

    # --- unlike by other user triggers owner notification (optional behavior you added) ---
    before = owner.notifications.count()
    r = c2.post(f"/api/community/v2/projects/{project_id}/unlike/")
    assert r.status_code in (200, 201), r.content

    owner.refresh_from_db()
    assert owner.notifications.count() == before + 1
    msg = owner.notifications.latest("created_at").message.lower()
    assert "unliked your project" in msg

    # --- self-like by owner should NOT notify themselves (guard present in model) ---
    before = owner.notifications.count()
    r = c1.post(f"/api/community/v2/projects/{project_id}/like/")
    assert r.status_code in (200, 201), r.content
    owner.refresh_from_db()
    assert owner.notifications.count() == before  # no self-notification

    # (cleanup: self-unlike also should not notify)
    r = c1.post(f"/api/community/v2/projects/{project_id}/unlike/")
    assert r.status_code in (200, 201), r.content
