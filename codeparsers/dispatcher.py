# codeparsers/dispatcher.py
from .graph import build_project_graph
from .parsers import PythonParser, CParser, CssParser, HtmlParser, JsParser

def parse_code(language: str, file_name: str, file_content: str, all_files: dict | None = None):
    language = (language or "").lower().strip()
    all_files = all_files or {}

    # Project-wide graph mode
    if language in {"project", "multi", "all"}:
        files = dict(all_files)
        files[file_name] = file_content
        global_results, file_results = build_project_graph(files)
        return {"global": global_results, "files": file_results}

    # Single-file modes
    if language == "python":
        p = PythonParser(file_name, file_content); p.parse()
        return p.get_python_relations()
    if language == "c":
        p = CParser(file_name, file_content, all_files); p.parse()
        return p.get_c_relations()
    if language in {"js", "javascript"}:
        p = JsParser(file_name, file_content, all_files); p.parse()
        return p.get_js_relations()
    if language == "css":
        p = CssParser(file_name, file_content, all_files); p.parse()
        # optional: match selectors to any provided HTML
        html_parsers = []
        for name, content in all_files.items():
            if name.lower().endswith(".html"):
                hp = HtmlParser(name, content, all_files); hp.parse([])
                html_parsers.append(hp)
        if html_parsers:
            p.match_html_tags(html_parsers)
        return p.get_css_relations()
    if language == "html":
        css_parsers = []
        for name, content in all_files.items():
            if name.lower().endswith(".css"):
                cp = CssParser(name, content, all_files); cp.parse()
                css_parsers.append(cp)
        p = HtmlParser(file_name, file_content, all_files); p.parse(css_parsers)
        return p.get_html_relations()

    raise ValueError("Unsupported language. Use: python | c | css | html | js | project")
