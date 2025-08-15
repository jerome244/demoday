import json
from django.urls import reverse

def test_parse_api_python(client):
    url = reverse("codeparsers-parse")
    payload = {
        "language": "python",
        "file_name": "sample.py",
        "file_content": "def hi():\n    pass\n# note\nx = lambda y: y+1",
    }
    resp = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert resp.status_code == 200
    data = resp.json()["result"]
    assert any(f["name"] == "hi" for f in data["defined"])
    assert any(c["comment"] == "note" for c in data["comments"])
