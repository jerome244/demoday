# community/tests/test_import_github.py
import io, zipfile, json, types
import pytest
from django.urls import reverse
from asgiref.sync import sync_to_async
from community.models import Project, User, ProjectFile

@pytest.mark.django_db
def test_import_github_public(monkeypatch, client):
    # Build a tiny zip with a top-level folder like GitHub's zipball
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/app.py", "print('hi')\n")
        z.writestr("repo-abcdef/README.md", "# readme\n")
    data = buf.getvalue()

    class FakeResp:
        status_code = 200
        def iter_content(self, chunk_size=8192):
            yield data
    def fake_get(url, headers=None, stream=True, timeout=30):
        return FakeResp()

    monkeypatch.setattr("community.views.requests.get", fake_get)

    # Create project
    u = User.objects.create_user(username="alice", password="x")
    p = Project.objects.create(name="p", creator=u)

    url = reverse("community:project-import-github", args=[p.id])
    resp = client.post(url, data=json.dumps({
        "repo_url": "https://github.com/owner/repo",
        "ref": "main",
    }), content_type="application/json")

    assert resp.status_code == 200
    assert resp.json()["imported_files"] >= 2

    assert ProjectFile.objects.filter(project=p, path="app.py").exists()
    assert ProjectFile.objects.filter(project=p, path="README.md").exists()

@pytest.mark.django_db
def test_import_github_subdir(monkeypatch, client):
    # Zip with subdirs
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/web/index.html", "<h1>hi</h1>\n")
        z.writestr("repo-abcdef/api/app.py", "print('api')\n")
    data = buf.getvalue()

    class FakeResp:
        status_code = 200
        def iter_content(self, chunk_size=8192):
            yield data
    def fake_get(url, headers=None, stream=True, timeout=30):
        return FakeResp()

    monkeypatch.setattr("community.views.requests.get", fake_get)

    u = User.objects.create_user(username="alice", password="x")
    p = Project.objects.create(name="p", creator=u)

    url = reverse("community:project-import-github", args=[p.id])
    resp = client.post(url, data=json.dumps({
        "repo_url": "https://github.com/owner/repo",
        "subdir": "web",
    }), content_type="application/json")

    assert resp.status_code == 200
    # Only 'web' files are ingested; api/ is ignored
    assert ProjectFile.objects.filter(project=p, path="index.html").exists()
    assert not ProjectFile.objects.filter(project=p, path="app.py").exists()
