import json
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

def test_project_graph_edges_and_metrics_via_parse_api(api_client: APIClient):
    """
    Calls /api/code/parse/ with language='project' and a tiny multi-file project.
    Verifies edges, called_by, and metrics presence and basic correctness.
    """
    payload = {
        "language": "project",
        "file_name": "main.py",
        "file_content": (
            "from pkg.util import hello\n"
            "\n"
            "def run():\n"
            "    hello()\n"
        ),
        "all_files": {
            "pkg/util.py": (
                "def hello():\n"
                "    return 1\n"
            ),
            "pkg/extra.py": "# just a comment\n",
        },
    }

    r = api_client.post(
        "/api/code/parse/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert r.status_code == 200

    data = r.json()["result"]
    g = data["global"]

    # new graph keys exist
    for key in ("edges", "called_by", "imports_resolved", "metrics"):
        assert key in g

    # edge from run() -> hello() should exist
    assert any(
        e.get("to", {}).get("func") == "hello"
        and e.get("from", {}).get("func") == "run"
        for e in g["edges"]
    )

    # called_by index should list a callsite for hello
    assert "hello" in g["called_by"]
    assert any(cb.get("file") == "main.py" for cb in g["called_by"]["hello"])

    # metrics include both files and have non-zero word counts
    assert "main.py" in g["metrics"]
    assert "pkg/util.py" in g["metrics"]
    assert g["metrics"]["main.py"]["words"] > 0
    assert g["metrics"]["pkg/util.py"]["num_functions"] >= 1
