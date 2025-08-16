# codeparsers/tests/test_html_css_match.py
import pytest
from codeparsers.parsers import parse_code

def test_html_css_class_and_id_match_basic():
    html = '<div class="test btn" id="hero"></div>'
    css  = '.test { color:red; } .btn:hover { cursor:pointer; } #hero { margin:0; }'

    css_rel = parse_code("css", "styles.css", css, {})
    assert ".test" in css_rel["class_selectors"]
    assert ".btn"  in css_rel["class_selectors"]
    assert "#hero" in css_rel["id_selectors"]

    # HTML parse builds its own CssParser from all_files mapping:
    html_rel = parse_code("html", "index.html", html, {"styles.css": css})
    matched = html_rel["matched_css"]
    # Should match class tokens and id token (normalized)
    assert ".test" in matched
    assert ".btn"  in matched
    assert "#hero" in matched
    # Each match should reference the html file/tag/attributes
    for k in (".test", ".btn", "#hero"):
        assert matched[k][0]["file"] == "index.html"
        assert matched[k][0]["tag"]  == "div"

def test_css_multi_selectors_and_combinators():
    css = """
    div .card.primary:hover, .badge::after { color: blue; }
    #app, main #root { display: block; }
    """
    rel = parse_code("css", "ui.css", css, {})
    # classes extracted from anywhere in selector (and stripped of pseudos)
    assert ".card" in rel["class_selectors"]
    assert ".primary" in rel["class_selectors"]
    assert ".badge" in rel["class_selectors"]
    # ids collected too
    assert "#app" in rel["id_selectors"]

def test_html_supports_className_and_whitespace_split():
    html = '<section><span className="alpha beta  gamma"></span></section>'
    css  = '.alpha{ } .beta{ } .gamma{ }'
    html_rel = parse_code("html", "page.html", html, {"styles.css": css})
    matched = html_rel["matched_css"]
    # Every className token should match
    assert {".alpha", ".beta", ".gamma"}.issubset(set(matched.keys()))
