import io
import json
import zipfile
import pytest

from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from community.models import Project, User, ProjectFile


pytestmark = pytest.mark.django_db


def _build_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr(path, content)
    return buf.getvalue()


def _find_child(node, name, typ=None):
    for ch in node.get("children", []):
        if ch["name"] == name and (typ is None or ch["type"] == typ):
            return ch
    return None


def test_tree_from_manual_files(client):
    u = User.objects.create_user(username="alice", password="x")
    p = Project.objects.create(name="proj", creator=u)

    # create files directly to simulate an already-ingested project
    ProjectFile.objects.create(project=p, path="index.html", content="<h1>x</h1>\n")
    ProjectFile.objects.create(project=p, path="assets/styles.css", content=".a{ }\n")
    ProjectFile.objects.create(project=p, path="server/api.py", content="def f():\n    pass\n")

    url = reverse("community:project-file-tree", args=[p.id])
    r = client.get(url)
    assert r.status_code == 200
    data = r.json()
    tree = data["tree"]

    # root
    assert tree["type"] == "dir" and tree["name"] == "/"

    # index.html at root
    assert _find_child(tree, "index.html", "file") is not None

    # assets/styles.css nested
    assets = _find_child(tree, "assets", "dir"); assert assets
    assert _find_child(assets, "styles.css", "file") is not None

    # server/api.py nested
    server = _find_child(tree, "server", "dir"); assert server
    assert _find_child(server, "api.py", "file") is not None

    # sorted: dirs first then files (alpha)
    names_in_root = [c["name"] for c in tree["children"]]
    assert names_in_root == sorted(names_in_root, key=lambda n: (n == "index.html", n))  # 'assets','server','index.html'

    assert data["total_files"] == 3


def test_tree_from_zip_upload(client):
    u = User.objects.create_user(username="bob", password="x")
    p = Project.objects.create(name="zipproj", creator=u)

    zbytes = _build_zip({
        "index.html": "<h1>hi</h1>\n",
        "a/b/c.txt": "ok\n",
        "a/d.txt": "x\n",
    })

    up = reverse("community:project-upload-zip", args=[p.id])
    resp = client.post(
        up,
        {"file": SimpleUploadedFile("proj.zip", zbytes, content_type="application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["ingested"] >= 3

    url = reverse("community:project-file-tree", args=[p.id])
    r = client.get(url)
    assert r.status_code == 200
    tree = r.json()["tree"]

    # root file
    assert _find_child(tree, "index.html", "file")

    # nested: a/b/c.txt and a/d.txt
    a = _find_child(tree, "a", "dir"); assert a
    b = _find_child(a, "b", "dir"); assert b
    assert _find_child(b, "c.txt", "file")
    assert _find_child(a, "d.txt", "file")


def test_tree_from_github_import(client, monkeypatch):
    # simulate GitHub zipball with top-level folder (repo-abcdef/)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/public/index.html", "<h1>hey</h1>\n")
        z.writestr("repo-abcdef/public/styles.css", ".x{ }\n")
        z.writestr("repo-abcdef/api/server.py", "def api():\n    return 1\n")
    data = buf.getvalue()

    class FakeResp:
        status_code = 200
        def iter_content(self, chunk_size=8192):
            yield data

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

    tree_url = reverse("community:project-file-tree", args=[p.id])
    r = client.get(tree_url)
    assert r.status_code == 200
    tree = r.json()["tree"]

    # structure should be flattened without the top folder
    public = _find_child(tree, "public", "dir"); assert public
    assert _find_child(public, "index.html", "file")
    assert _find_child(public, "styles.css", "file")

    api = _find_child(tree, "api", "dir"); assert api
    assert _find_child(api, "server.py", "file")
