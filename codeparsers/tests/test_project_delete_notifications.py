import json
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


def test_project_delete_notifies_other_participants():
    # --- owner + two participants ---
    owner_u, owner_p = f"alice_{_rand()}", "Passw0rd!123"
    bob_u, bob_p     = f"bob_{_rand()}",   "Passw0rd!123"
    eve_u, eve_p     = f"eve_{_rand()}",   "Passw0rd!123"

    owner_id = make_user(owner_u, f"{owner_u}@ex.com", owner_p)
    bob_id   = make_user(bob_u,   f"{bob_u}@ex.com",   bob_p)
    eve_id   = make_user(eve_u,   f"{eve_u}@ex.com",   eve_p)

    t_owner = get_token(owner_u, owner_p)
    c_owner = auth_client(t_owner)

    # --- owner creates project ---
    proj_name = f"proj-{_rand()}"
    r = c_owner.post(
        "/api/community/v2/projects/",
        {"name": proj_name, "description": "", "creator": owner_id},
        format="json",
    )
    assert r.status_code in (200, 201), r.content
    pid = r.json()["id"]

    # --- add Bob & Eve as participants (creator-only action) ---
    for uid in (bob_id, eve_id):
        r = c_owner.post(f"/api/community/v2/projects/{pid}/add_participant/", {"user_id": uid}, format="json")
        assert r.status_code in (200, 201), r.content

    U = get_user_model()
    bob = U.objects.get(pk=bob_id)
    eve = U.objects.get(pk=eve_id)
    bob_before = bob.notifications.count()
    eve_before = eve.notifications.count()

    # --- delete the project (creator) -> should notify all non-creator participants ---
    r = c_owner.delete(f"/api/community/v2/projects/{pid}/")  # DRF default returns 204
    assert r.status_code in (204, 200), r.content

    bob.refresh_from_db()
    eve.refresh_from_db()
    assert bob.notifications.count() == bob_before + 1
    assert eve.notifications.count() == eve_before + 1

    last_bob = bob.notifications.latest("created_at").message.lower()
    last_eve = eve.notifications.latest("created_at").message.lower()
    assert "has been deleted" in last_bob and proj_name.lower() in last_bob
    assert "has been deleted" in last_eve and proj_name.lower() in last_eve
