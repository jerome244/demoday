import json
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from community.models import Thread

pytestmark = pytest.mark.django_db


def api_auth(client: APIClient, token: str) -> APIClient:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def thread_with_participants(user, other_user):
    t = Thread.objects.create(title="jwt-protected")
    t.participants.add(user, other_user)
    return t


def test_jwt_obtain_refresh_and_use_on_protected_endpoint(api_client, client, user, thread_with_participants):
    # 1) obtain access/refresh
    r = client.post(
        "/api/auth/token/",
        {"username": user.username, "password": "pass1234"},
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.json()
    assert "access" in data and "refresh" in data
    access = data["access"]

    # 2) refresh token
    r2 = client.post("/api/auth/token/refresh/", {"refresh": data["refresh"]}, content_type="application/json")
    assert r2.status_code == 200 and "access" in r2.json()

    # 3) use access on a protected endpoint (requires IsAuthenticated): add thread message
    c = api_auth(api_client, access)
    resp = c.post(f"/api/community/v2/threads/{thread_with_participants.id}/add_message/", {"content": "hello jwt"})
    assert resp.status_code in (200, 201)


def test_jwt_wrong_password_fails(client, user):
    r = client.post(
        "/api/auth/token/",
        {"username": user.username, "password": "WRONG"},
        content_type="application/json",
    )
    assert r.status_code in (400, 401)  # SimpleJWT usually 401


def test_jwt_invalid_refresh_fails(client):
    r = client.post("/api/auth/token/refresh/", {"refresh": "not-a-token"}, content_type="application/json")
    assert r.status_code in (400, 401)


def test_blocked_user_token_or_access_denied(api_client, client, user, thread_with_participants):
    """
    This test supports BOTH configurations:
    - If you wired BlockAwareTokenObtainPairView: token obtain should fail (400/401/403).
    - If not: token obtain may succeed, but any protected API call must be denied by NotBlocked (403).
    """
    # block user at the model level
    user.block()

    # try to obtain token
    r = client.post(
        "/api/auth/token/",
        {"username": user.username, "password": "pass1234"},
        content_type="application/json",
    )

    if r.status_code in (400, 401, 403):
        # Block-aware obtain view: correct behavior
        return

    # Otherwise token was issued; using it on protected endpoint must be denied by NotBlocked
    access = r.json()["access"]
    c = api_auth(APIClient(), access)
    resp = c.post(f"/api/community/v2/threads/{thread_with_participants.id}/add_message/", {"content": "should fail"})
    assert resp.status_code in (401, 403)
