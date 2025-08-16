import json
import pytest
from django.urls import reverse
from community.models import Project, User, ProjectFile

pytestmark = pytest.mark.django_db


def _create_project_with_file(path: str, content: str):
    u = User.objects.create_user(username="u", password="x")
    p = Project.objects.create(name="p", creator=u)
    ProjectFile.objects.create(project=p, path=path, content=content)
    return p


def test_get_with_lint_python_ok(client):
    p = _create_project_with_file("main.py", "def f():\n    return 1\n")
    url = reverse("community:project-file-detail", args=[p.id, "main.py"])
    r = client.get(url + "?lint=1")
    assert r.status_code == 200
    data = r.json()
    assert data["path"] == "main.py"
    assert isinstance(data.get("diagnostics"), list)
    assert data["diagnostics"] == []  # no syntax errors


def test_get_with_lint_python_syntax_error(client):
    p = _create_project_with_file("oops.py", "def f(:\n    pass\n")
    url = reverse("community:project-file-detail", args=[p.id, "oops.py"])
    r = client.get(url + "?lint=1")
    assert r.status_code == 200
    diags = r.json().get("diagnostics", [])
    assert diags and diags[0]["severity"] == "error"
    assert diags[0]["source"] == "python"
    # has LSP-like range keys
    assert "range" in diags[0] and "start" in diags[0]["range"]


def test_put_preview_format_and_lint_python(client):
    p = _create_project_with_file("fmt.py", "x=1\n")
    url = reverse("community:project-file-detail", args=[p.id, "fmt.py"])
    messy = "def  f (  ):\n    return  (1+2)\n"
    r = client.put(
        url + "?preview=1&format=1&lint=1",
        data=json.dumps({"content": messy}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.json()
    # preview returns formatted but does not save
    assert data.get("preview") is True
    assert "formatted" in data
    # diagnostics should be empty for valid code
    assert data.get("diagnostics") == []

    # GET again; content should still be original file content (not the messy one)
    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.json()["content"] == "x=1\n"


def test_put_save_format_and_lint_python(client):
    p = _create_project_with_file("fmt_save.py", "x=1\n")
    url = reverse("community:project-file-detail", args=[p.id, "fmt_save.py"])
    messy = "def  g ( ):\n    return( 41+1)\n"
    r = client.put(
        url + "?format=1&lint=1",
        data=json.dumps({"content": messy}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.json()
    assert data["saved"] is True
    assert "content" in data
    # Tool can be "black" (if installed) or "none"; both acceptable for CI
    assert data.get("tool") in ("black", "none")
    # Regardless of tool, content is normalized to have a trailing newline
    assert data["content"].endswith("\n")
    # On GET we should see saved content
    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.json()["content"] == data["content"]


def test_lint_css_unbalanced_brace(client):
    p = _create_project_with_file("styles.css", ".a { color: red; \n")  # missing closing }
    url = reverse("community:project-file-detail", args=[p.id, "styles.css"])
    r = client.get(url + "?lint=1")
    assert r.status_code == 200
    diags = r.json().get("diagnostics", [])
    # our lightweight CSS linter should flag an error
    assert any(d.get("severity") == "error" for d in diags)
