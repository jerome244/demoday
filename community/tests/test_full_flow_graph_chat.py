import io
import json
import zipfile
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from community.models import Project, ProjectFile

def make_zip(files: dict[str, str]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return bio.getvalue()

@pytest.mark.django_db
def test_full_flow_graph_chat_edit_download(client):
    User = get_user_model()

    # --- Users & Project (sharing) ---
    owner = User.objects.create_user(username="owner", password="pw")
    member = User.objects.create_user(username="member", password="pw")
    outsider = User.objects.create_user(username="outsider", password="pw")

    project = Project.objects.create(name="GraphProj", creator=owner)
    project.participants.add(member)  # share with member

    # --- Upload ZIP (ingest -> ProjectFile rows) ---
    files = {
        "README.md": "# Demo\n",
        "src/app.py": 'print("hello")\n',
        "src/utils/helpers.py": "def add(a,b):\n    return a+b\n",
    }
    zip_bytes = make_zip(files)
    upload = SimpleUploadedFile("code.zip", zip_bytes, content_type="application/zip")

    resp_up = client.post(f"/api/community/projects/{project.id}/upload-zip/", {"file": upload})
    assert resp_up.status_code == 200
    assert resp_up.json()["ingested"] == len(files)

    # verify DB matches (this is the source for your Cytoscape graph)
    paths = set(ProjectFile.objects.filter(project=project).values_list("path", flat=True))
    assert paths == set(files.keys())

    # --- Graph prefetch (bulk) ---
    bulk_q = ",".join(files.keys())
    resp_bulk = client.get(f"/api/community/projects/{project.id}/files/bulk/?paths={bulk_q}")
    assert resp_bulk.status_code == 200
    bulk = resp_bulk.json()
    assert bulk["project_id"] == project.id
    for p in files.keys():
        assert bulk["files"][p]["found"] is True
        assert isinstance(bulk["files"][p]["content"], str)

    # --- Read + Edit a file (GET -> ETag -> PUT If-Match) ---
    file_path = "src/app.py"
    url_file = f"/api/community/projects/{project.id}/files/{file_path}/"

    r_get = client.get(url_file)
    assert r_get.status_code == 200
    etag = r_get.headers.get("ETag")
    assert etag
    assert r_get.json()["content"] == files[file_path]

    new_src = 'print("changed!")\n'
    r_put = client.put(
        url_file,
        data=json.dumps({"content": new_src}),
        content_type="application/json",
        **{"HTTP_IF_MATCH": etag},
    )
    assert r_put.status_code == 200
    assert r_put.json()["content"] == new_src

    # DB updated?
    pf = ProjectFile.objects.get(project=project, path=file_path)
    assert pf.content == new_src

    # --- Chat on graph screen (project-wide chat) ---
    # Endpoints enforce request.user membership: log in as owner
    client.force_login(owner)

    # ensure chat thread exists & participants set
    r_info = client.get(f"/api/community/projects/{project.id}/chat/")
    assert r_info.status_code == 200
    info = r_info.json()
    assert info["project_id"] == project.id
    assert any(p["username"] == "owner" for p in info["participants"])
    assert any(p["username"] == "member" for p in info["participants"])

    # member posts a message
    r_post1 = client.post(
        f"/api/community/projects/{project.id}/chat/messages/add/",
        data=json.dumps({"sender_id": member.id, "content": "hi owner"}),
        content_type="application/json",
    )
    assert r_post1.status_code == 200
    msg1 = r_post1.json()
    assert msg1["content"] == "hi owner"

    # owner replies
    r_post2 = client.post(
        f"/api/community/projects/{project.id}/chat/messages/add/",
        data={"sender_id": owner.id, "content": "hi member"},
    )
    assert r_post2.status_code == 200

    # outsider should be forbidden
    r_post3 = client.post(
        f"/api/community/projects/{project.id}/chat/messages/add/",
        data={"sender_id": outsider.id, "content": "let me in"},
    )
    assert r_post3.status_code == 403

    # list messages (pagination)
    r_list = client.get(f"/api/community/projects/{project.id}/chat/messages/?page=1&per_page=10")
    assert r_list.status_code == 200
    lst = r_list.json()
    assert lst["count"] >= 2
    assert len(lst["results"]) >= 2
    # newest first; capture the lowest id as baseline
    first_seen_id = min(m["id"] for m in lst["results"])

    # incremental fetch after id
    r_after = client.get(f"/api/community/projects/{project.id}/chat/messages/?after_id={first_seen_id}")
    assert r_after.status_code == 200
    inc = r_after.json()["results"]
    assert all(m["id"] > first_seen_id for m in inc)

    # --- Download zip and verify edited content is inside ---
    r_dl = client.get(f"/api/community/projects/{project.id}/download.zip")
    assert r_dl.status_code == 200
    assert r_dl["Content-Type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r_dl.content)) as zf:
        names = set(zf.namelist())
        assert names == set(files.keys())
        # file content should be updated to new_src
        assert zf.read(file_path).decode("utf-8") == new_src
