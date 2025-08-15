import json
from django.urls import reverse
import pytest

pytestmark = pytest.mark.django_db

def post_parse(client, payload):
    url = reverse("codeparsers-parse")
    return client.post(url, data=json.dumps(payload), content_type="application/json")

def test_python_parser_method_attr_calls(client):
    content = """
class Foo:
    def bar(self): pass

f = Foo()
f.bar()  # attribute call
"""
    resp = post_parse(client, {"language":"python","file_name":"x.py","file_content":content})
    assert resp.status_code == 200
    called = resp.json()["result"]["called"]
    assert "bar" in called  # attribute call picked up

def test_c_parser_function_pointer_detection(client):
    c = """
void test() {}
void (*fp)() = test;
fp();
"""
    resp = post_parse(client, {"language":"c","file_name":"a.c","file_content":c})
    assert resp.status_code == 200
    res = resp.json()["result"]
    fps = res["function_pointers"]
    # has assignment and call entries
    assert any(x.get("function") == "test" and x.get("pointer") == "fp" for x in fps)
    assert any(x.get("pointer") == "fp" and "function" not in x for x in fps)

def test_css_parser_match_html_tags_exercised(client):
    # Hit CssParser.match_html_tags path (different from HTML->CSS match)
    html = '<div class="card">x</div><h2 id="title">T</h2>'
    css = ".card { padding: 1rem; } #title { font-weight: bold; }"
    # First parse CSS via /api using language 'css' so it builds class/id lists
    resp_css = post_parse(client, {"language":"css","file_name":"s.css","file_content":css})
    assert resp_css.status_code == 200
    # Now emulate CssParser.match_html_tags by calling HTML with all_files
    resp_html = post_parse(client, {
        "language":"html",
        "file_name":"index.html",
        "file_content":html,
        "all_files":{"s.css": css}
    })
    assert resp_html.status_code == 200
    matched = resp_html.json()["result"]["matched_css"]
    assert ".card" in matched and "#title" in matched

def test_js_parser_comment_capture(client):
    js = """
// top comment
/* block
   comment */
function run() {}
run();
"""
    resp = post_parse(client, {"language":"js","file_name":"s.js","file_content":js})
    assert resp.status_code == 200
    comments = resp.json()["result"]["comments"]
    joined = " ".join(c["comment"] for c in comments)
    assert "top comment" in joined and "block" in joined
