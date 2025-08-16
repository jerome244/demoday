import io
import json
import zipfile
import pytest
from django.urls import reverse

from community.models import Project, User, ProjectFile

pytestmark = pytest.mark.django_db


def test_project_summary_basic(client):
    u = User.objects.create_user(username="alice", password="x")
    p = Project.objects.create(name="proj", creator=u)

    ProjectFile.objects.create(project=p, path="a.py", content="def foo():\n    bar()\n")
    ProjectFile.objects.create(project=p, path="b.py", content="def bar():\n    return 1\n")
    ProjectFile.objects.create(project=p, path="app.js", content="function start(){ run() } function run(){} start();")
    ProjectFile.objects.create(project=p, path="index.html", content='<div class="card" id="root"></div>\n')
    ProjectFile.objects.create(project=p, path="styles.css", content=".card{ } #root{ }")

    url = reverse("community:project-summary", args=[p.id])
    r = client.get(url)
    assert r.status_code == 200

    data = r.json()
    assert data["project_id"] == p.id
    assert set(data["file_paths"]) == {"a.py", "b.py", "app.js", "index.html", "styles.css"}
    assert data["totals"]["files"] == 5
    # language breakdown from filenames
    assert data["languages"]["python"] == 2
    assert data["languages"]["javascript"] == 1
    assert data["languages"]["html"] == 1
    assert data["languages"]["css"] == 1
    # the parser-specific payload should be present and be a dict
    assert isinstance(data["summary"], dict) and data["summary"]


def test_project_summary_after_github_import(client, monkeypatch):
    # Build a tiny zip in memory
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/public/index.html", '<div class="box"></div>\n')
        z.writestr("repo-abcdef/public/styles.css", ".box{ color:red; }")
        z.writestr("repo-abcdef/app.js", "function ping(){ return 1 } ping();")
    data = buf.getvalue()

    class FakeResp:
        status_code = 200
        def iter_content(self, chunk_size=8192):
            yield data

    # IMPORTANT: patch what the view actually calls
    monkeypatch.setattr("community.views.requests.get", lambda *a, **k: FakeResp())

    u = User.objects.create_user(username="gh", password="x")
    p = Project.objects.create(name="ghproj", creator=u)

    imp = reverse("community:project-import-github", args=[p.id])
    r = client.post(
        imp,
        data=json.dumps({"repo_url": "https://github.com/owner/repo", "ref": "main"}),
        content_type="application/json",
    )
    assert r.status_code == 200


