import io, zipfile, json
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

pytestmark = pytest.mark.django_db

def auth(api_client, token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client

def make_zip_bytes(files: dict[str,str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buf.seek(0)
    return buf.read()

# ---------- Users ----------

def test_user_create_hashes_password(api_client, admin_access_token):
    c = auth(api_client, admin_access_token)
    payload = {"username": "newguy", "email": "new@example.com", "password": "Passw0rd!"}
    r = c.post("/api/community/v2/users/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code in (200, 201)
    U = get_user_model()
    u = U.objects.get(username="newguy")
    assert u.check_password("Passw0rd!")
    assert u.password != "Passw0rd!"

def test_admin_can_block_unblock_user(api_client, admin_access_token, user):
    c = auth(api_client, admin_access_token)
    r = c.post(f"/api/community/v2/users/{user.id}/block/")
    assert r.status_code == 200 and "blocked" in r.json()["detail"].lower()
    r2 = c.post(f"/api/community/v2/users/{user.id}/unblock/")
    assert r2.status_code == 200 and "unblocked" in r2.json()["detail"].lower()

# ---------- Projects ----------

def test_project_crud_and_like_flow(api_client, access_token, user):
    c = auth(api_client, access_token)
    # create
    payload = {"name": "ProjV2", "description": "d", "creator": user.id}
    r = c.post("/api/community/v2/projects/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code in (200, 201)
    proj_id = r.json()["id"]
    # like/unlike
    assert c.post(f"/api/community/v2/projects/{proj_id}/like/").status_code == 200
    assert c.post(f"/api/community/v2/projects/{proj_id}/unlike/").status_code == 200

def test_project_upload_and_download_zip(api_client, access_token, user):
    c = auth(api_client, access_token)

    # create
    r = c.post(
        "/api/community/v2/projects/",
        data=json.dumps({"name": "ZipV2", "description": "", "creator": user.id}),
        content_type="application/json",
    )
    proj_id = r.json()["id"]

    # upload
    zbytes = make_zip_bytes({"a.txt": "hi", "src/app.py": "print(1)"})
    up = SimpleUploadedFile("demo.zip", zbytes, content_type="application/zip")
    r2 = c.post(f"/api/community/v2/projects/{proj_id}/upload-zip/", {"file": up})
    assert r2.status_code == 200 and r2.json()["ingested"] == 2

    # download
    r3 = c.get(f"/api/community/v2/projects/{proj_id}/download.zip/")
    assert r3.status_code == 200
    assert "attachment" in r3.get("Content-Disposition", "").lower()

    # FileResponse streams: collect bytes once
    body = b"".join(r3.streaming_content)
    assert body[:2] == b"PK"  # zip signature

    # (optional) verify zip contents match what we uploaded
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = set(zf.namelist())
    assert {"a.txt", "src/app.py"} <= names

def test_blocked_user_denied(api_client, access_token, user):
    # block user (directly via model)
    user.block()
    c = auth(api_client, access_token)
    r = c.get("/api/community/v2/projects/")
    assert r.status_code in (401, 403)

# ---------- Threads ----------

def test_thread_add_message_and_like(api_client, access_token, thread_with_participants, user):
    c = auth(api_client, access_token)
    tid = thread_with_participants.id
    r = c.post(f"/api/community/v2/threads/{tid}/add_message/", {"content": "hello v2"})
    assert r.status_code in (200, 201)
    msg_id = r.json()["id"]
    assert c.post(f"/api/community/v2/threads/{tid}/messages/{msg_id}/like/").status_code == 200
    assert c.post(f"/api/community/v2/threads/{tid}/messages/{msg_id}/unlike/").status_code == 200

# ---------- Conversations ----------

def test_conversation_add_message_like(api_client, access_token, conversation_between, user):
    c = auth(api_client, access_token)
    cid = conversation_between.id
    r = c.post(f"/api/community/v2/conversations/{cid}/add_message/", {"content": "hi dm"})
    assert r.status_code in (200, 201)
    pm_id = r.json()["id"]
    assert c.post(f"/api/community/v2/conversations/{cid}/messages/{pm_id}/like/").status_code == 200
    assert c.post(f"/api/community/v2/conversations/{cid}/messages/{pm_id}/unlike/").status_code == 200
