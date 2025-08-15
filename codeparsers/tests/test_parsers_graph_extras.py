# codeparsers/tests/test_parsers_graph_extras.py
import io, zipfile, json, pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

def make_zip(files: dict) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return bio.getvalue()

def test_graph_edges_and_metrics(api_client: APIClient):
    z = make_zip({
        "pkg/mod.py": "def foo():\n    bar()\n\ndef bar():\n    pass\n",
        "main.py": "from pkg import mod\n\ndef run():\n    mod.foo()\n",
    })
    up = {"file": io.BytesIO(z)}
    up["file"].name = "demo.zip"
    r = api_client.post("/api/code/parse-zip/", data=up, format="multipart")
    assert r.status_code == 200
    g = r.json()["global"]
    # new keys exist
    for k in ("edges","called_by","imports_resolved","metrics"):
        assert k in g
    # edge present
    assert any(e["to"]["func"] == "foo" for e in g["edges"])
