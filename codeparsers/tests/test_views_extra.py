import json
from django.urls import reverse
import pytest
from codeparsers.models import ParseResult

pytestmark = pytest.mark.django_db

def test_parse_api_save_true_persists_and_str(client):
    url = reverse("codeparsers-parse")
    payload = {
        "language":"python","file_name":"x.py",
        "file_content":"def a(): pass","save": True
    }
    r = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    body = r.json()
    pr = ParseResult.objects.get(pk=body["id"])
    assert "python" in str(pr).lower()  # hit __str__

def test_parse_api_invalid_json_400(client):
    url = reverse("codeparsers-parse")
    r = client.post(url, data="{", content_type="application/json")  # invalid json
    assert r.status_code == 400

def test_parse_api_unsupported_language_400(client):
    url = reverse("codeparsers-parse")
    payload = {"language":"go","file_name":"x.go","file_content":"func main(){}"}
    r = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 400
