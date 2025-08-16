# community/parsing.py
from __future__ import annotations

from typing import Dict, Any, List, Set, DefaultDict
from collections import defaultdict

from codeparsers.parsers import parse_code


def _is(path: str, *exts: str) -> bool:
    p = (path or "").lower()
    return any(p.endswith(e) for e in exts)


def parse_project_files(files: Dict[str, str]) -> Dict[str, Any]:
    """
    Build a project graph from {path: content} using codeparsers.parse_code.

    Nodes:
      - file:<path>
      - py.def:<name> / js.def:<name> / c.def:<name>
      - css.class:<name> / css.id:<name>

    Edges:
      - defines:    file -> def
      - calls:      file -> def (same-language, name-based)
      - uses-style: HTML file -> CSS class/id
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    # file nodes
    for path in files:
        nodes.setdefault(f"file:{path}", {"id": f"file:{path}", "type": "file", "label": path})

    # aggregates
    py_defs: DefaultDict[str, Set[str]] = defaultdict(set)
    py_calls: DefaultDict[str, Set[str]] = defaultdict(set)

    js_defs: DefaultDict[str, Set[str]] = defaultdict(set)
    js_calls: DefaultDict[str, Set[str]] = defaultdict(set)

    c_defs: DefaultDict[str, Set[str]] = defaultdict(set)
    c_calls: DefaultDict[str, Set[str]] = defaultdict(set)

    css_classes: Set[str] = set()
    css_ids: Set[str] = set()

    html_results: Dict[str, Dict[str, Any]] = {}
    css_map = {p: c for p, c in files.items() if _is(p, ".css")}

    # run per-file parsers
    for path, content in files.items():
        if _is(path, ".py"):
            rel = parse_code("python", path, content, files)
            for d in rel.get("defined", []):
                n = d.get("name")
                if n:
                    py_defs[n].add(path)
            for n in (rel.get("called") or {}).keys():
                if n:
                    py_calls[n].add(path)

        elif _is(path, ".js"):
            rel = parse_code("js", path, content, files)
            for d in rel.get("defined", []):
                n = d.get("name")
                if n:
                    js_defs[n].add(path)
            for d in rel.get("arrow_functions", []):
                n = d.get("name")
                if n:
                    js_defs[n].add(path)
            for n in (rel.get("called") or {}).keys():
                if n:
                    js_calls[n].add(path)

        elif _is(path, ".c", ".h"):
            rel = parse_code("c", path, content, files)
            for d in rel.get("defined", []):
                n = d.get("name")
                if n:
                    c_defs[n].add(path)
            for n in (rel.get("called") or {}).keys():
                if n:
                    c_calls[n].add(path)

        elif _is(path, ".css"):
            rel = parse_code("css", path, content, files)
            for cls in rel.get("class_selectors", []):
                if cls.startswith("."):
                    css_classes.add(cls[1:])
            for i in rel.get("id_selectors", []):
                if i.startswith("#"):
                    css_ids.add(i[1:])

        elif _is(path, ".html", ".htm"):
            # pass CSS map so HtmlParser can populate matched_css
            rel = parse_code("html", path, content, css_map)
            html_results[path] = rel

    # symbol nodes
    for n in py_defs:
        nodes.setdefault(f"py.def:{n}", {"id": f"py.def:{n}", "type": "py.def", "label": n})
    for n in js_defs:
        nodes.setdefault(f"js.def:{n}", {"id": f"js.def:{n}", "type": "js.def", "label": n})
    for n in c_defs:
        nodes.setdefault(f"c.def:{n}", {"id": f"c.def:{n}", "type": "c.def", "label": n})
    for n in css_classes:
        nodes.setdefault(f"css.class:{n}", {"id": f"css.class:{n}", "type": "css.class", "label": f".{n}"})
    for n in css_ids:
        nodes.setdefault(f"css.id:{n}", {"id": f"css.id:{n}", "type": "css.id", "label": f"#{n}"})

    # defines edges
    for n, paths in py_defs.items():
        for p in paths:
            edges.append({"from": f"file:{p}", "to": f"py.def:{n}", "type": "defines"})
    for n, paths in js_defs.items():
        for p in paths:
            edges.append({"from": f"file:{p}", "to": f"js.def:{n}", "type": "defines"})
    for n, paths in c_defs.items():
        for p in paths:
            edges.append({"from": f"file:{p}", "to": f"c.def:{n}", "type": "defines"})

    # calls edges (simple name-based within same language)
    for n, callers in py_calls.items():
        if n in py_defs:
            for p in callers:
                edges.append({"from": f"file:{p}", "to": f"py.def:{n}", "type": "calls"})
    for n, callers in js_calls.items():
        if n in js_defs:
            for p in callers:
                edges.append({"from": f"file:{p}", "to": f"js.def:{n}", "type": "calls"})
    for n, callers in c_calls.items():
        if n in c_defs:
            for p in callers:
                edges.append({"from": f"file:{p}", "to": f"c.def:{n}", "type": "calls"})

    # HTML uses CSS (from HtmlParser.matched_css)
    for html_path, rel in html_results.items():
        for sel in (rel.get("matched_css") or {}).keys():
            if sel.startswith("."):
                cls = sel[1:]
                if cls in css_classes:
                    edges.append({"from": f"file:{html_path}", "to": f"css.class:{cls}", "type": "uses-style"})
            elif sel.startswith("#"):
                i = sel[1:]
                if i in css_ids:
                    edges.append({"from": f"file:{html_path}", "to": f"css.id:{i}", "type": "uses-style"})

    return {"nodes": list(nodes.values()), "edges": edges}


def build_project_summary(files: Dict[str, str]) -> Dict[str, Any]:
    # aggregates
    py_defs: DefaultDict[str, Set[str]] = defaultdict(set)
    py_calls: DefaultDict[str, Set[str]] = defaultdict(set)
    js_defs: DefaultDict[str, Set[str]] = defaultdict(set)
    js_calls: DefaultDict[str, Set[str]] = defaultdict(set)
    c_defs:  DefaultDict[str, Set[str]] = defaultdict(set)
    c_calls: DefaultDict[str, Set[str]] = defaultdict(set)

    css_classes_def: DefaultDict[str, Set[str]] = defaultdict(set)  # class -> css files
    css_ids_def:     DefaultDict[str, Set[str]] = defaultdict(set)  # id    -> css files
    css_classes_use: DefaultDict[str, Set[str]] = defaultdict(set)  # class -> html files
    css_ids_use:     DefaultDict[str, Set[str]] = defaultdict(set)  # id    -> html files
    html_uses: Dict[str, Dict[str, List[str]]] = {}  # html file -> {classes, ids}

    css_map = {p: c for p, c in files.items() if _is(p, ".css")}

    for path, content in files.items():
        if _is(path, ".py"):
            rel = parse_code("python", path, content, files)
            for d in rel.get("defined", []):
                n = d.get("name")
                if n: py_defs[n].add(path)
            for n in (rel.get("called") or {}):
                py_calls[n].add(path)

        elif _is(path, ".js"):
            rel = parse_code("js", path, content, files)
            for d in rel.get("defined", []):
                n = d.get("name")
                if n: js_defs[n].add(path)
            for d in rel.get("arrow_functions", []):
                n = d.get("name")
                if n: js_defs[n].add(path)
            for n in (rel.get("called") or {}):
                js_calls[n].add(path)

        elif _is(path, ".c", ".h"):
            rel = parse_code("c", path, content, files)
            for d in rel.get("defined", []):
                n = d.get("name")
                if n: c_defs[n].add(path)
            for n in (rel.get("called") or {}):
                c_calls[n].add(path)

        elif _is(path, ".css"):
            rel = parse_code("css", path, content, files)
            for sel in rel.get("class_selectors", []):
                if sel.startswith("." ):
                    css_classes_def[sel[1:]].add(path)
            for sel in rel.get("id_selectors", []):
                if sel.startswith("#"):
                    css_ids_def[sel[1:]].add(path)

        elif _is(path, ".html", ".htm"):
            rel = parse_code("html", path, content, css_map)
            classes, ids = [], []
            for sel in (rel.get("matched_css") or {}):
                if sel.startswith("."):
                    cls = sel[1:]
                    css_classes_use[cls].add(path)
                    classes.append(cls)
                elif sel.startswith("#"):
                    i = sel[1:]
                    css_ids_use[i].add(path)
                    ids.append(i)
            html_uses[path] = {"classes": sorted(set(classes)), "ids": sorted(set(ids))}

    def _sym_list(lang: str, defs: dict, calls: dict) -> List[Dict[str, Any]]:
        names = sorted(set(defs.keys()) | set(calls.keys()))
        out = []
        for n in names:
            out.append({
                "language": lang,
                "name": n,
                "defined_in": sorted(defs.get(n, [])),
                "called_from": sorted(calls.get(n, [])),
            })
        return out

    symbols: List[Dict[str, Any]] = []
    symbols += _sym_list("python", py_defs, py_calls)
    symbols += _sym_list("javascript", js_defs, js_calls)
    symbols += _sym_list("c", c_defs, c_calls)

    styles = {
        "classes": [
            {"name": k, "defined_in_css": sorted(css_classes_def.get(k, [])),
             "used_by_html": sorted(css_classes_use.get(k, []))}
            for k in sorted(set(css_classes_def.keys()) | set(css_classes_use.keys()))
        ],
        "ids": [
            {"name": k, "defined_in_css": sorted(css_ids_def.get(k, [])),
             "used_by_html": sorted(css_ids_use.get(k, []))}
            for k in sorted(set(css_ids_def.keys()) | set(css_ids_use.keys()))
        ],
    }

    return {
        "files": sorted(files.keys()),
        "symbols": symbols,
        "styles": styles,
        "html_usage": [{"file": f, **html_uses[f]} for f in sorted(html_uses.keys())],
        "totals": {
            "files": len(files),
            "symbols": len(symbols),
            "css_classes": len(styles["classes"]),
            "css_ids": len(styles["ids"]),
        },
    }


# Optional compatibility alias
def parse_project(files: Dict[str, str]) -> Dict[str, Any]:
    return parse_project_files(files)
