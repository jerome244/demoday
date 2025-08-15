# codeparsers/tests/test_css_html_matching.py
import json, pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

def test_css_html_cross_linking_in_project(api_client: APIClient):
    payload = {
        "language": "project",
        "file_name": "index.html",
        "file_content": '<div id="hero" class="btn"></div>',
        "all_files": {
            "styles.css": ".btn { color: red; } #hero { padding: 1rem; }",
        },
    }
    r = api_client.post("/api/code/parse/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    res = r.json()["result"]
    g = res["global"]

    # CSS global matched_html present for styles.css
    assert "matched_html" in g["css"]
    assert "styles.css" in g["css"]["matched_html"]
    mh = g["css"]["matched_html"]["styles.css"]
    assert ".btn" in mh and "#hero" in mh

    # HTML global matched_css present for index.html
    assert "matched_css" in g["html"]
    assert "index.html" in g["html"]["matched_css"]
    mc = g["html"]["matched_css"]["index.html"]
    assert ".btn" in mc and "#hero" in mc
