import json, io, zipfile, pytest
from rest_framework.test import APIClient
from community.models import ProjectInvitation

pytestmark = pytest.mark.django_db

def auth(c: APIClient, token: str) -> APIClient:
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c

def test_save_unsave_and_list(api_client, access_token, user):
    c = auth(api_client, access_token)
    # create project
    r = c.post(
        "/api/community/v2/projects/",
        data=json.dumps({"name": "SaveMe", "description": "", "creator": user.id}),
        content_type="application/json",
    )
    assert r.status_code in (200, 201)
    proj_id = r.json()["id"]

    # save
    r2 = c.post(f"/api/community/v2/projects/{proj_id}/save/")
    assert r2.status_code == 200

    # list saved
    r3 = c.get("/api/community/v2/projects/saved/me/")
    assert r3.status_code == 200
    data = r3.json()
    items = data.get("results", data)
    assert any(p["id"] == proj_id for p in items)

    # unsave
    r4 = c.post(f"/api/community/v2/projects/{proj_id}/unsave/")
    assert r4.status_code == 200


def test_invite_accept_decline_revoke(api_client, access_token, admin_access_token, user, other_user, client):
    # user creates project
    c = auth(api_client, access_token)
    r = c.post(
        "/api/community/v2/projects/",
        data=json.dumps({"name": "InvProj", "description": "", "creator": user.id}),
        content_type="application/json",
    )
    assert r.status_code in (200, 201)
    proj_id = r.json()["id"]

    # invite other_user
    r2 = c.post(f"/api/community/v2/projects/{proj_id}/invite/", data={"invitee_id": other_user.id})
    assert r2.status_code == 201
    inv_id = r2.json()["id"]

    # other_user obtains token and accepts
    r_tok = client.post(
        "/api/auth/token/",
        {"username": other_user.username, "password": "pass1234"},
        content_type="application/json",
    )
    other_access = r_tok.json()["access"]
    c_other = auth(APIClient(), other_access)

    r3 = c_other.post(f"/api/community/v2/projects/{proj_id}/invitations/{inv_id}/accept/")
    assert r3.status_code == 200

    # admin creates another invite and revokes it
    c_admin = auth(APIClient(), admin_access_token)
    r4 = c_admin.post(
        "/api/community/v2/projects/",
        data=json.dumps({"name": "RevokeProj", "description": "", "creator": user.id}),
        content_type="application/json",
    )
    proj2_id = r4.json()["id"]

    r5 = c_admin.post(f"/api/community/v2/projects/{proj2_id}/invite/", data={"invitee_id": other_user.id})
    assert r5.status_code == 201
    inv2_id = r5.json()["id"]

    r6 = c_admin.post(f"/api/community/v2/projects/{proj2_id}/invitations/{inv2_id}/revoke/")
    assert r6.status_code == 200
    assert ProjectInvitation.objects.get(pk=inv2_id).status == "REVOKED"
