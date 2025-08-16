import io
import json
import zipfile
import pytest
from django.contrib.auth import get_user_model
from community.models import Project, ProjectFile

def build_zip(files: dict[str, str]) -> io.BytesIO:
    """Create an in-memory zip from a path->content dict."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    bio.seek(0)
    return bio

@pytest.mark.django_db
def test_upload_zip__graph_created__list_files__download_zip(client):
    # Arrange: user + empty project
    User = get_user_model()
    user = User.objects.create_user(username="alice", password="pw")
    project = Project.objects.create(name="ZipProj", creator=user)

    # A small codebase with nested path
    files = {
        "README.md": "# Demo\n",
        "src/app.py": 'print("hello")\n',
        "src/utils/helpers.py": "def add(a,b):\n    return a+b\n",
    }
    z = build_zip(files)

    # Act: upload the zip to your existing upload endpoint
    url_upload = f"/api/community/projects/{project.id}/upload-zip/"
    resp = client.post(url_upload, {"file": z}, format="multipart")
    assert resp.status_code == 200
    assert resp.json()["ingested"] == len(files)

    # Assert: DB rows exist (this is the source for your Cytoscape graph)
    paths = set(ProjectFile.objects.filter(project=project).values_list("path", flat=True))
    assert paths == set(files.keys())

    # Optional: test your helper that represents the “graph source”
    assert set(project.project_tree()) == set(files.keys())

    # Act: download generated zip and verify content/paths
    url_dl = f"/api/community/projects/{project.id}/download.zip"
    dl = client.get(url_dl)
    assert dl.status_code == 200
    assert dl["Content-Type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
        names = set(zf.namelist())
        assert names == set(files.keys())
        assert zf.read("src/app.py").decode("utf-8").startswith('print("hello")')

@pytest.mark.django_db
def test_edit_and_save__etag_conflict__bulk_prefetch(client):
    # Arrange
    User = get_user_model()
    user = User.objects.create_user(username="bob", password="pw")
    project = Project.objects.create(name="EditProj", creator=user)
    pf = ProjectFile.objects.create(project=project, path="src/app.py", content='print("hello")\n')

    # 1) GET file (like opening a Cytoscape popup)
    url_file = f"/api/community/projects/{project.id}/files/{pf.path}/"
    r1 = client.get(url_file)
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag
    assert r1.json()["content"].startswith('print("hello")')

    # 2) PUT new content with If-Match (save edit)
    new_src = 'print("changed!")\n'
    r2 = client.put(url_file, data=json.dumps({"content": new_src}), content_type="application/json", **{"HTTP_IF_MATCH": etag})
    assert r2.status_code == 200
    assert r2.json()["content"] == new_src
    pf.refresh_from_db()
    assert pf.content == new_src

    # 3) Simulate a concurrent change in DB to test ETag mismatch
    pf.content = 'print("someone else wrote this")\n'
    pf.save(update_fields=["content"])

    # Try to save again with the stale ETag => expect 412
    r3 = client.put(url_file, data=json.dumps({"content": "print('my stale write')\n"}), content_type="application/json", **{"HTTP_IF_MATCH": etag})
    assert r3.status_code == 412
    assert "ETag mismatch" in r3.json()["detail"]

    # 4) Bulk prefetch (for fast popup open on multiple nodes)
    ProjectFile.objects.create(project=project, path="README.md", content="# Hi\n")
    url_bulk = f"/api/community/projects/{project.id}/files/bulk/?paths=src/app.py,README.md,missing.txt"
    r4 = client.get(url_bulk)
    assert r4.status_code == 200
    files = r4.json()["files"]
    assert files["src/app.py"]["found"] is True and "someone else wrote this" in files["src/app.py"]["content"]
    assert files["README.md"]["found"] is True and files["README.md"]["content"].startswith("# Hi")
    assert files["missing.txt"]["found"] is False
