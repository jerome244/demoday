import pytest
from django.urls import reverse
from community.models import Project, User, ProjectFile

pytestmark = pytest.mark.django_db


def test_project_graph_matches_calls_and_styles(client):
    # create user + project
    u = User.objects.create_user(username="alice", password="x")
    p = Project.objects.create(name="proj", creator=u)

    # seed files
    files = {
        # Python: a.py calls bar(), b.py declares bar()
        "a.py": "def foo():\n    bar()\n",
        "b.py": "def bar():\n    return 1\n",

        # JS: start() calls run(), run() declared
        "app.js": "function start(){ run() } function run(){} start();",

        # HTML/CSS: class & id used by HTML, defined in CSS
        "index.html": '<div class="card" id="root"></div>\n',
        "styles.css": ".card{ } #root{ }",
    }
    for path, content in files.items():
        ProjectFile.objects.create(project=p, path=path, content=content)

    # call the graph endpoint
    url = reverse("community:project-graph", args=[p.id])
    resp = client.get(url)
    assert resp.status_code == 200

    graph = resp.json()["graph"]
    nodes = {n["id"] for n in graph["nodes"]}
    edges = {(e["type"], e["from"], e["to"]) for e in graph["edges"]}

    # nodes present
    assert "file:a.py" in nodes
    assert "file:b.py" in nodes
    assert "file:app.js" in nodes
    assert "file:index.html" in nodes
    assert "file:styles.css" in nodes

    assert "py.def:bar" in nodes
    assert "js.def:start" in nodes
    assert "js.def:run" in nodes
    assert "css.class:card" in nodes
    assert "css.id:root" in nodes

    # python: defines & calls
    assert ("defines", "file:b.py", "py.def:bar") in edges
    assert ("calls",   "file:a.py", "py.def:bar") in edges

    # js: defines & calls
    assert ("defines", "file:app.js", "js.def:start") in edges
    assert ("defines", "file:app.js", "js.def:run")   in edges
    assert ("calls",   "file:app.js", "js.def:run")   in edges

    # html uses css
    assert ("uses-style", "file:index.html", "css.class:card") in edges
    assert ("uses-style", "file:index.html", "css.id:root")    in edges
