import json
import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

def post_parse(client, payload):
    url = reverse("codeparsers-parse")
    return client.post(url, data=json.dumps(payload), content_type="application/json")

def test_python_parser_def_lambda_calls(client):
    payload = {
        "language": "python",
        "file_name": "x.py",
        "file_content": "def hi():\n    pass\n# note\nx = lambda y: y+1\nhi()\n",
    }
    resp = post_parse(client, payload)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert any(f["name"] == "hi" for f in result["defined"])
    assert any(c["comment"] == "note" for c in result["comments"])
    assert "hi" in result["called"]

def test_js_parser_arrow_and_calls(client):
    content = "const add = () => { return 1; }; callMe();"
    payload = {"language": "js", "file_name": "a.js", "file_content": content}
    resp = post_parse(client, payload)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert any(a["name"] == "add" for a in result["arrow_functions"])
    assert "callMe" in result["called"]

def test_html_css_matching_classes_and_ids(client):
    html = '<div class="btn">Hi</div><h1 id="title">T</h1>'
    css = ".btn { color: red; } #title{ font-weight: bold; }"
    payload = {
        "language": "html",
        "file_name": "index.html",
        "file_content": html,
        "all_files": {"styles.css": css},
    }
    resp = post_parse(client, payload)
    assert resp.status_code == 200
    result = resp.json()["result"]
    matched = result["matched_css"]
    # Should have entries for .btn and #title
    assert ".btn" in matched and "#title" in matched
    # Matched records mention index.html and tags
    assert matched[".btn"][0]["file"] == "index.html"
    assert matched["#title"][0]["tag"] == "h1"
