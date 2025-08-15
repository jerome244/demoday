# codeparsers/graph.py
import re
from .parsers import PythonParser, JsParser, CParser, CssParser, HtmlParser

def build_project_graph(files: dict):
    """
    files: { "path/to/file.py": "content", ... }
    returns (global_results, file_results)
    """
    global_results = {
        "defined": [],
        "lambda_functions": [],
        "called": {},
        "comments": [],
        "html": {},
        "css": {},
        "js": {},
        # extras for graphing:
        "edges": [],
        "called_by": {},
        "imports_resolved": {},
        "metrics": {},
    }
    file_results = {}

    py_parsers, js_parsers, c_parsers = {}, {}, {}
    css_parsers, html_parsers = {}, {}

    # -------- PASS 1: parse everything, but store CSS/HTML parsers for cross-linking
    for name, content in files.items():
        if name.endswith(".py"):
            p = PythonParser(name, content); p.parse()
            py_parsers[name] = p
            rel = p.get_python_relations()
            global_results["defined"].extend(rel["defined"])
            global_results["lambda_functions"].extend(rel["lambda_functions"])
            for func, calls in rel["called"].items():
                global_results["called"].setdefault(func, []).extend(calls)
            global_results["comments"].extend(rel["comments"])
            file_results[name] = rel

        elif name.endswith(".js"):
            p = JsParser(name, content, files); p.parse()
            js_parsers[name] = p
            rel = p.get_js_relations()
            global_results["js"].setdefault("functions", []).extend(rel["defined"])
            global_results["js"].setdefault("comments", []).extend(rel["comments"])
            for func, calls in rel["called"].items():
                global_results["js"].setdefault("called", {}).setdefault(func, []).extend(calls)
            file_results[name] = rel

        elif name.endswith(".c"):
            p = CParser(name, content, files); p.parse()
            c_parsers[name] = p
            rel = p.get_c_relations()
            global_results.setdefault("c", {}).setdefault("defined", []).extend(rel["defined"])
            for func, calls in rel["called"].items():
                global_results.setdefault("c", {}).setdefault("called", {}).setdefault(func, []).extend(calls)
            global_results["comments"].extend(rel["comments"])
            file_results[name] = rel

        elif name.endswith(".css"):
            p = CssParser(name, content, files); p.parse()
            css_parsers[name] = p
            rel = p.get_css_relations()
            # store raw selectors/comments now; matched_html will be filled after cross-linking
            global_results["css"].setdefault("selectors", []).extend(rel["selectors"])
            global_results["css"].setdefault("comments", []).extend(rel["comments"])
            file_results[name] = rel  # will be updated later with matched_html

        elif name.endswith(".html"):
            # parse HTML without CSS linking yet; we’ll link after we’ve parsed all CSS
            p = HtmlParser(name, content, files)
            # temporarily pass empty css_parsers; we’ll call p._match_css() later
            p.parse([])  # fills tags/comments/scripts/styles
            html_parsers[name] = p
            rel = p.get_html_relations()
            global_results["html"].setdefault("tags", []).extend(rel["tags"])
            global_results["html"].setdefault("comments", []).extend(rel["comments"])
            file_results[name] = rel  # will be updated later with matched_css

        else:
            file_results[name] = {"content": content}

    # -------- PASS 2: cross-link CSS <-> HTML both ways
    css_list = list(css_parsers.values())
    html_list = list(html_parsers.values())

    # HTML: attach matched_css using the actual CSS parsers
    for name, hp in html_parsers.items():
        hp._match_css(css_list)  # use your existing method
        file_results[name] = hp.get_html_relations()  # now includes matched_css

    # CSS: attach matched_html using parsed HTML
    for name, cp in css_parsers.items():
        cp.match_html_tags(html_list)
        file_results[name] = cp.get_css_relations()  # now includes matched_html

    # Also surface a combined view at the global level if you want
    global_results["css"]["matched_html"] = {
        name: cp.get_css_relations()["matched_html"] for name, cp in css_parsers.items()
    }
    global_results["html"]["matched_css"] = {
        name: hp.get_html_relations()["matched_css"] for name, hp in html_parsers.items()
    }

    # -------- PASS 3: Python edges + called_by + imports + metrics (unchanged)
    def_index = {}
    for d in global_results["defined"]:
        def_index.setdefault(d["name"], []).append({
            "file": d.get("file"),
            "line": d.get("line"),
            "end_line": d.get("end_line"),
        })

    for callee, calls in global_results["called"].items():
        for call in calls:
            global_results["called_by"].setdefault(callee, []).append(call)

    for fname, parser in py_parsers.items():
        for call in parser.get_python_relations().get("calls", []):
            callee = call.get("callee")
            match = def_index.get(callee, [])
            global_results["edges"].append({
                "from": {"file": fname, "func": call.get("caller")},
                "to": {"func": callee, "file": match[0]["file"] if match else None},
                "line": call.get("line"),
                "kind": call.get("kind"),
            })

    def resolve_module(mod):
        if not mod: return None
        cand = mod.replace(".", "/") + ".py"
        return cand if cand in files else None

    for fname, parser in py_parsers.items():
        resolved = []
        for imp in parser.get_python_relations().get("imports", []):
            mod = imp["module"] or (imp["names"][0] if imp["names"] else None)
            resolved.append({**imp, "resolved_file": resolve_module(mod)})
        global_results["imports_resolved"][fname] = resolved

    for fname, content in files.items():
        words = len(re.findall(r"\b\w+\b", content))
        num_defs = sum(1 for d in global_results["defined"] if d.get("file") == fname)
        num_calls = 0
        if fname in py_parsers:
            num_calls += len(py_parsers[fname].get_python_relations().get("calls", []))
        if fname in js_parsers:
            num_calls += sum(len(v) for v in js_parsers[fname].get_js_relations().get("called", {}).values())
        if fname in c_parsers:
            num_calls += sum(len(v) for v in c_parsers[fname].get_c_relations().get("called", {}).values())
        global_results["metrics"][fname] = {"words": words, "num_functions": num_defs, "num_calls": num_calls}

    return global_results, file_results
