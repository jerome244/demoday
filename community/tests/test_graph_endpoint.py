# community/tests/test_graph_endpoint.py
import io, zipfile, json, pytest
from django.urls import reverse
from community.models import Project, User, ProjectFile

pytestmark = pytest.mark.django_db

def _fake_zipball():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("repo-abcdef/a.js", "function foo(){bar()}")    # decl foo, call bar
        z.writestr("repo-abcdef/b.js", "function bar(){}")
    return buf.getvalue()

class _FakeResp:
    status_code = 200
    def __init__(self, data): self._data = data
    def iter_content(self, chunk_size=8192):
        yield self._data

def test_graph_after_github_import(monkeypatch, client, settings):
    # Patch GitHub download and parser
    data = _fake_zipball()
    monkeypatch.setattr("community.views.requests.get", lambda *a, **k: _FakeResp(data))

    def fake_parse(files: dict):
        # files == {"a.js": "...", "b.js": "..."}
        return {
            "nodes": [{"id": "foo"}, {"id": "bar"}],
            "edges": [{"from": "foo", "to": "bar", "type": "calls"}],
        }
    monkeypatch.setattr("codeparsers.parsers.parse_project", fake_parse, raising=False)

    u = User.objects.create_user(username="alice", password="x")
    p = Project.objects.create(name="p", creator=u)

    # import
    import_url = reverse("community:project-import-github", args=[p.id])
    resp = client.post(import_url, data=json.dumps({
        "repo_url": "https://github.com/owner/repo", "ref": "main"
    }), content_type="application/json")
    assert resp.status_code == 200

    # graph
    graph_url = reverse("community:project-graph", args=[p.id])
    resp = client.get(graph_url)
    assert resp.status_code == 200
    graph = resp.json()["graph"]
    assert len(graph["nodes"]) == 2
    assert graph["edges"][0]["type"] == "calls"
