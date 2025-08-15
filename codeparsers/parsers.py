import ast
import logging
import re
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def _append_unique(bucket: Dict[str, List[Dict[str, Any]]], key: str, item: Dict[str, Any]) -> None:
    lst = bucket.setdefault(key, [])
    if item not in lst:
        lst.append(item)

# codeparsers/parsers.py
class PythonParser:
    def __init__(self, file_name, file_content):
        self.file_name = file_name
        self.file_content = file_content
        self.tree = ast.parse(file_content)

        self.function_definitions = []   # [{name,line,end_line,word_count,docstring,file}]
        self.lambda_functions = []       # [{name:'lambda', line, file}]
        self.function_calls = {}         # {callee: [{file,line,caller}]}
        self.calls = []                  # edges list: [{caller, callee, line, kind, text, file}]
        self.comments = []               # [{line, comment, file}]
        self.imports = []                # [{type,module,names,level,line,file}]

    def parse(self):
        self._parse_function_definitions()
        self._parse_lambda_functions()
        self._parse_function_calls_and_imports()
        self._parse_comments()

    # ---------- helpers
    def _src_seg(self, node):
        try:
            return ast.get_source_segment(self.file_content, node) or ""
        except Exception:
            return ""

    def _slice(self, start, end):
        lines = self.file_content.splitlines()
        start = max(1, start); end = max(start, end or start)
        return "\n".join(lines[start-1:end])

    def _words(self, text):
        return len(re.findall(r"\b\w+\b", text))

    # ---------- defs
    def _parse_function_definitions(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", start)
                body_text = self._slice(start, end)
                self.function_definitions.append({
                    "name": node.name,
                    "line": start,
                    "end_line": end,
                    "word_count": self._words(body_text),
                    "docstring": ast.get_docstring(node) or "",
                    "file": self.file_name,
                })

    # ---------- lambdas
    def _parse_lambda_functions(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Lambda):
                self.lambda_functions.append({
                    "name": "lambda",
                    "line": getattr(node, "lineno", None),
                    "file": self.file_name,
                })

    # ---------- calls + imports
    def _parse_function_calls_and_imports(self):
        class Walker(ast.NodeVisitor):
            def __init__(self, outer):
                self.o = outer
                self.stack = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            # imports
            def visit_Import(self, node):
                self.o.imports.append({
                    "type": "import",
                    "module": None,
                    "names": [a.name for a in node.names],
                    "level": 0,
                    "line": getattr(node, "lineno", None),
                    "file": self.o.file_name,
                })

            def visit_ImportFrom(self, node):
                self.o.imports.append({
                    "type": "from",
                    "module": node.module,
                    "names": [a.name for a in node.names],
                    "level": getattr(node, "level", 0) or 0,
                    "line": getattr(node, "lineno", None),
                    "file": self.o.file_name,
                })

            # calls
            def visit_Call(self, node):
                line = getattr(node, "lineno", None)
                caller = self.stack[-1] if self.stack else None

                callee, kind = None, "name"
                if isinstance(node.func, ast.Name):
                    callee = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    callee, kind = node.func.attr, "attribute"
                else:
                    kind = type(node.func).__name__

                rec = {
                    "file": self.o.file_name,
                    "line": line,
                    "caller": caller,
                    "callee": callee,
                    "kind": kind,
                    "text": self.o._src_seg(node),
                }
                self.o.calls.append(rec)
                if callee:
                    self.o.function_calls.setdefault(callee, []).append({
                        "file": self.o.file_name,
                        "line": line,
                        "caller": caller,
                    })
                self.generic_visit(node)

        Walker(self).visit(self.tree)

    # ---------- comments
    def _parse_comments(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            if "#" in line:
                self.comments.append({
                    "line": i,
                    "comment": line.split("#", 1)[1].strip(),
                    "file": self.file_name,
                })

    def get_python_relations(self):
        return {
            "defined": self.function_definitions,
            "lambda_functions": self.lambda_functions,
            "called": self.function_calls,
            "calls": self.calls,
            "imports": self.imports,
            "comments": self.comments,
        }

class CParser:
    def __init__(self, file_name, file_content, all_files):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.function_definitions = []
        self.function_calls = {}
        self.function_pointers = []
        self.comments = []

    def parse(self):
        self._parse_function_definitions()
        self._parse_function_calls()
        self._parse_function_pointers()
        self._parse_comments()

    def _parse_function_definitions(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            m = re.search(r"\b([A-Za-z_]\w*)\s*\([^)]*\)\s*{", line)
            if m:
                self.function_definitions.append({"name": m.group(1), "line": i, "file": self.file_name})

    def _parse_function_calls(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            for call in re.findall(r"\b([A-Za-z_]\w*)\s*\(", line):
                self.function_calls.setdefault(call, []).append({"file": self.file_name, "line": i})

    def _parse_function_pointers(self):
        assigns = re.findall(r"\s*\(\*\s*(\w+)\s*\)\s*\(\)\s*=\s*(\w+)\s*;", self.file_content)
        for ptr, func in assigns:
            self.function_pointers.append({"pointer": ptr, "function": func, "file": self.file_name})
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            for ptr in re.findall(r"\b([A-Za-z_]\w*)\s*\(\)\s*;", line):
                self.function_pointers.append({"pointer": ptr, "file": self.file_name, "line": i})

    def _parse_comments(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            m = re.search(r"//(.*)", line)
            if m:
                self.comments.append({"line": i, "comment": m.group(1).strip()})
        for i, m in enumerate(re.findall(r"/\*.*?\*/", self.file_content, re.DOTALL), start=1):
            self.comments.append({"line": i, "comment": m.strip()})

    def get_c_relations(self):
        return {
            "defined": self.function_definitions,
            "called": self.function_calls,
            "function_pointers": self.function_pointers,
            "comments": self.comments,
        }


class CssParser:
    def __init__(self, file_name: str, file_content: str, all_files: Dict[str, str]):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.selectors: List[Dict[str, Any]] = []
        self.comments: List[Dict[str, Any]] = []
        self.class_selectors: List[str] = []
        self.id_selectors: List[str] = []
        self.matched_html: Dict[str, List[Dict[str, Any]]] = {}

    def parse(self) -> None:
        self._parse_selectors()
        self._parse_comments()

    # in CssParser._parse_selectors
    def _parse_selectors(self) -> None:
        selector_pattern = r'([a-zA-Z0-9\s\.\#\-\:\,\>\+\~]+)\s*\{(.*?)\}'
        matches = re.findall(selector_pattern, self.file_content, re.DOTALL)
        for selector, properties in matches:
            properties_dict = self._parse_properties(properties)
            selector_clean = selector.strip()
            self.selectors.append({"selector": selector_clean, "properties": properties_dict})

            # NEW: extract all .classes and #ids from the full selector string
            class_tokens = re.findall(r'\.([A-Za-z_][\w\-]*)', selector_clean)
            id_tokens    = re.findall(r'\#([A-Za-z_][\w\-]*)', selector_clean)

            for cls in class_tokens:
                s = f".{cls}"
                if s not in self.class_selectors:
                    self.class_selectors.append(s)
            for ident in id_tokens:
                s = f"#{ident}"
                if s not in self.id_selectors:
                    self.id_selectors.append(s)

    def _parse_properties(self, properties_string: str) -> Dict[str, str]:
        properties: Dict[str, str] = {}
        for prop, value in re.findall(r"([a-zA-Z\-]+)\s*:\s*([^;]+);", properties_string):
            properties[prop.strip()] = value.strip()
        return properties

    def _parse_comments(self) -> None:
        for match in re.finditer(r"/\*(.*?)\*/", self.file_content, re.DOTALL):
            line = self.file_content.count("\n", 0, match.start()) + 1
            self.comments.append({"line": line, "comment": match.group(1).strip()})

    def match_html_tags(self, html_parsers: List["HtmlParser"]) -> None:
        for html_parser in html_parsers:
            for tag in html_parser.tags:
                attrs = tag["attributes"]
                classes = set((attrs.get("class") or "").split())

                # class selectors
                for selector in self.class_selectors:
                    cls_name = selector[1:]
                    if cls_name in classes:
                        _append_unique(self.matched_html, selector, {
                            "html_file": html_parser.file_name,
                            "tag": tag["tag"],
                            "attributes": attrs,
                        })

                # id selectors
                tid = attrs.get("id")
                if tid:
                    for selector in self.id_selectors:
                        if tid == selector[1:]:
                            _append_unique(self.matched_html, selector, {
                                "html_file": html_parser.file_name,
                                "tag": tag["tag"],
                                "attributes": attrs,
                            })

    def get_css_relations(self) -> Dict[str, Any]:
        return {
            "selectors": self.selectors,
            "class_selectors": self.class_selectors,
            "id_selectors": self.id_selectors,
            "comments": self.comments,
            "matched_html": self.matched_html,
        }


class HtmlParser:
    def __init__(self, file_name: str, file_content: str, all_files: Dict[str, str]):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.tags: List[Dict[str, Any]] = []
        self.comments: List[Dict[str, Any]] = []
        self.scripts: List[str] = []
        self.styles: List[str] = []
        self.matched_css: Dict[str, List[Dict[str, Any]]] = {}

    def parse(self, css_parsers: List[CssParser]) -> None:
        self._parse_tags()
        self._parse_comments()
        self._parse_scripts()
        self._parse_styles()
        self._match_css(css_parsers)

    def _parse_tags(self) -> None:
        for tag, attributes in re.findall(r"<([a-zA-Z0-9\-]+)([^>]*)>", self.file_content):
            self.tags.append({"tag": tag, "attributes": self._parse_attributes(attributes)})

    # in HtmlParser._parse_attributes
    def _parse_attributes(self, attributes_string: str) -> Dict[str, str]:
        attrs: Dict[str, str] = {}
        # supports key="value" or key='value'
        pattern = r'([a-zA-Z0-9_\-:]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')'
        for m in re.finditer(pattern, attributes_string):
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else m.group(3) or ""
            attrs[key] = val
        return attrs

    def _parse_comments(self) -> None:
        for match in re.finditer(r"<!--(.*?)-->", self.file_content, re.DOTALL):
            self.comments.append({"comment": match.group(1).strip()})

    def _parse_scripts(self) -> None:
        for script in re.findall(r"<script.*?>(.*?)</script>", self.file_content, re.DOTALL):
            self.scripts.append(script)

    def _parse_styles(self) -> None:
        for style in re.findall(r"<style.*?>(.*?)</style>", self.file_content, re.DOTALL):
            self.styles.append(style)

    def _match_css(self, css_parsers: List["CssParser"]) -> None:
        for css_parser in css_parsers:
            rel = css_parser.get_css_relations()
            class_selectors = rel["class_selectors"]
            id_selectors = rel["id_selectors"]

            for tag in self.tags:
                attrs = tag["attributes"]
                classes = set((attrs.get("class") or "").split())

                # class selectors
                for selector in class_selectors:
                    if selector[1:] in classes:
                        _append_unique(self.matched_css, selector, {
                            "file": self.file_name,
                            "tag": tag["tag"],
                            "attributes": attrs,
                        })

                # id selectors
                tid = attrs.get("id")
                if tid:
                    for selector in id_selectors:
                        if tid == selector[1:]:
                            _append_unique(self.matched_css, selector, {
                                "file": self.file_name,
                                "tag": tag["tag"],
                                "attributes": attrs,
                            })

    def get_html_relations(self) -> Dict[str, Any]:
        return {
            "tags": self.tags,
            "comments": self.comments,
            "scripts": self.scripts,
            "styles": self.styles,
            "matched_css": self.matched_css,
        }


class JsParser:
    def __init__(self, file_name, file_content, all_files):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.function_definitions = []
        self.function_calls = {}
        self.arrow_functions = []
        self.comments = []

    def parse(self):
        self._parse_function_definitions()
        self._parse_arrow_functions()
        self._parse_function_calls()
        self._parse_comments()

    def _parse_function_definitions(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            for fn in re.findall(r"\bfunction\s+([A-Za-z_]\w*)\s*\(", line):
                self.function_definitions.append({"name": fn, "line": i, "file": self.file_name})

    def _parse_arrow_functions(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            for name in re.findall(r"\b([A-Za-z_]\w*)\s*=\s*\([^)]*\)\s*=>", line):
                self.arrow_functions.append({"name": name, "line": i, "file": self.file_name})

    def _parse_function_calls(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            for call in re.findall(r"\b([A-Za-z_]\w*)\s*\(", line):
                self.function_calls.setdefault(call, []).append({"file": self.file_name, "line": i})

    def _parse_comments(self):
        for i, line in enumerate(self.file_content.splitlines(), start=1):
            m = re.search(r"//(.*)", line)
            if m:
                self.comments.append({"line": i, "comment": m.group(1).strip()})
        for i, m in enumerate(re.findall(r"/\*.*?\*/", self.file_content, re.DOTALL), start=1):
            self.comments.append({"line": i, "comment": m.strip()})

    def get_js_relations(self):
        return {
            "defined": self.function_definitions,
            "arrow_functions": self.arrow_functions,
            "called": self.function_calls,
            "comments": self.comments,
        }


# ---------- Convenience facade for Django views/services ----------


