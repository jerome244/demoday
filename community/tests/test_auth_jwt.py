import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

def test_obtain_and_refresh_jwt(client, user):
    # Obtain token
    url = reverse("token_obtain_pair")
    resp = client.post(url, {"username": user.username, "password": "pass1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access" in data and "refresh" in data

    # Refresh token
    ref_url = reverse("token_refresh")
    resp2 = client.post(ref_url, {"refresh": data["refresh"]})
    assert resp2.status_code == 200
    assert "access" in resp2.json()

def test_blocked_user_still_gets_token_by_default(client, user):
    """
    Our current model sets `blocked` but doesn't hook into auth.
    By default, SimpleJWT still issues tokens unless you add a custom auth backend.
    This test documents that behavior.
    """
    user.block()
    url = reverse("token_obtain_pair")
    resp = client.post(url, {"username": user.username, "password": "pass1234"})
    assert resp.status_code == 200, "Blocked users are not prevented from logging in by default"
