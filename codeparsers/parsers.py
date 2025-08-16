import ast
import logging
import re
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class PythonParser:
    def __init__(self, file_name: str, file_content: str):
        self.file_name = file_name
        self.file_content = file_content
        logger.debug("Parsing Python file: %s", self.file_name)
        self.tree = ast.parse(file_content)
        self.function_definitions: List[Dict[str, Any]] = []
        self.lambda_functions: List[Dict[str, Any]] = []
        self.function_calls: Dict[str, List[Dict[str, Any]]] = {}
        self.comments: List[Dict[str, Any]] = []

    def parse(self) -> None:
        self._parse_function_definitions()
        self._parse_lambda_functions()
        self._parse_function_calls()
        self._parse_comments()

    def _parse_function_definitions(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                self.function_definitions.append({
                    "name": node.name,
                    "line": node.lineno,
                })

    def _parse_lambda_functions(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Lambda):
                self.lambda_functions.append({
                    "name": "lambda",
                    "line": node.lineno,
                })

    def _parse_function_calls(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_function = node.func.id
                elif hasattr(node.func, "attr"):  # e.g. obj.method()
                    called_function = node.func.attr
                else:
                    continue
                self.function_calls.setdefault(called_function, []).append({
                    "file": self.file_name,
                    "line": node.lineno,
                })

    def _parse_comments(self) -> None:
        lines = self.file_content.splitlines()
        for lineno, line in enumerate(lines, start=1):
            stripped_line = line.strip()
            if "#" in stripped_line:
                comment = stripped_line.split("#", 1)[1].strip()
                logger.debug("Detected comment on %s:%d -> %s", self.file_name, lineno, comment)
                self.comments.append({"line": lineno, "comment": comment})

    def get_python_relations(self) -> Dict[str, Any]:
        return {
            "defined": self.function_definitions,
            "lambda_functions": self.lambda_functions,
            "called": self.function_calls,
            "comments": self.comments,
        }


class CParser:
    def __init__(self, file_name: str, file_content: str, all_files: Dict[str, str]):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.function_definitions: List[Dict[str, Any]] = []
        self.function_calls: Dict[str, List[Dict[str, Any]]] = {}
        self.function_pointers: List[Dict[str, Any]] = []
        self.comments: List[Dict[str, Any]] = []

    def parse(self) -> None:
        self._parse_function_definitions()
        self._parse_function_calls()
        self._parse_function_pointers()
        self._parse_comments()

    def _parse_function_definitions(self) -> None:
        function_defs = re.findall(r"\w+\s+\w+\s*\([^)]*\)\s*{", self.file_content)
        for func in function_defs:
            func_name = func.split("(")[0].split()[-1]
            self.function_definitions.append({"name": func_name})

    def _parse_function_calls(self) -> None:
        function_calls = re.findall(r"(\w+)\s*\(", self.file_content)
        for call in function_calls:
            self.function_calls.setdefault(call, []).append({"file": self.file_name})

    def _parse_function_pointers(self) -> None:
        pointer_assignments = re.findall(r"\s*\(\*\s*(\w+)\s*\)\s*\(\)\s*=\s*(\w+)\s*;", self.file_content)
        for ptr, func in pointer_assignments:
            self.function_pointers.append({"pointer": ptr, "function": func, "file": self.file_name})

        pointer_calls = re.findall(r"(\w+)\s*\(\)\s*;", self.file_content)
        for ptr in pointer_calls:
            self.function_pointers.append({"pointer": ptr, "file": self.file_name})

    def _parse_comments(self) -> None:
        # Single-line // comments
        for match in re.finditer(r"//(.*)", self.file_content):
            line = self.file_content.count("\n", 0, match.start()) + 1
            self.comments.append({"line": line, "comment": match.group(1).strip()})
        # Multi-line /* ... */
        for match in re.finditer(r"/\*.*?\*/", self.file_content, re.DOTALL):
            line = self.file_content.count("\n", 0, match.start()) + 1
            self.comments.append({"line": line, "comment": match.group(0).strip()})

    def get_c_relations(self) -> Dict[str, Any]:
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

    def _parse_selectors(self) -> None:
        """
        Extract selectors and properties, but also collect *all* class/id tokens
        that appear anywhere in the selector list (handles commas, combinators,
        and pseudo-classes).
        """
        # Match "selector_block { ... }" broadly (selectors can have commas/newlines)
        for selector_block, properties in re.findall(r'([^{]+)\{(.*?)\}', self.file_content, re.DOTALL):
            selector_block = selector_block.strip()
            properties_dict = self._parse_properties(properties)

            # Keep the raw selector block as-is for debugging
            self.selectors.append({"selector": selector_block, "properties": properties_dict})

            # Split by comma to handle ".a, .b, div .c"
            for sel in (s.strip() for s in selector_block.split(",")):
                if not sel:
                    continue
                # Find ALL class tokens like ".btn", ".test-2" (ignore pseudo like :hover by stopping at ':')
                for cls in re.findall(r'\.([A-Za-z_-][A-Za-z0-9_-]*)', sel):
                    token = f".{cls}"
                    if token not in self.class_selectors:
                        self.class_selectors.append(token)
                # Find ALL id tokens like "#hero"
                for i in re.findall(r'#([A-Za-z_-][A-Za-z0-9_-]*)', sel):
                    token = f"#{i}"
                    if token not in self.id_selectors:
                        self.id_selectors.append(token)

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
            for selector in self.class_selectors:
                for tag in html_parser.tags:
                    if tag["attributes"].get("class") == selector[1:]:
                        self.matched_html.setdefault(selector, []).append({
                            "html_file": html_parser.file_name,
                            "tag": tag["tag"],
                            "attributes": tag["attributes"],
                        })
            for selector in self.id_selectors:
                for tag in html_parser.tags:
                    if tag["attributes"].get("id") == selector[1:]:
                        self.matched_html.setdefault(selector, []).append({
                            "html_file": html_parser.file_name,
                            "tag": tag["tag"],
                            "attributes": tag["attributes"],
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

    def _parse_attributes(self, attributes_string: str) -> Dict[str, str]:
        attrs: Dict[str, str] = {}
        # supports data-attrs and single/double quotes
        for m in re.finditer(r'([a-zA-Z\-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')', attributes_string):
            name = m.group(1)
            val = m.group(3) if m.group(3) is not None else m.group(4) or ""
            attrs[name] = val
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

    def _match_css(self, css_parsers: List[CssParser]) -> None:
        # Precompute classes/ids present in this HTML file per tag
        for css_parser in css_parsers:
            css_rel = css_parser.get_css_relations()

            css_classes = set(css_rel.get("class_selectors", []))  # e.g. {".btn", ".test"}
            css_ids     = set(css_rel.get("id_selectors", []))     # e.g. {"#hero"}

            for tag in self.tags:
                # support both class and className (JSX)
                raw_class = tag["attributes"].get("class") or tag["attributes"].get("className") or ""
                class_tokens = [c for c in raw_class.split() if c]  # split on whitespace

                # For each class on the element, see if ".<class>" is declared in CSS
                for c in class_tokens:
                    tok = f".{c}"
                    if tok in css_classes:
                        self.matched_css.setdefault(tok, []).append({
                            "file": self.file_name,
                            "tag": tag["tag"],
                            "attributes": tag["attributes"],
                        })

                # IDs are single-valued; match if "#<id>" exists
                raw_id = tag["attributes"].get("id", "")
                if raw_id:
                    tok = f"#{raw_id}"
                    if tok in css_ids:
                        self.matched_css.setdefault(tok, []).append({
                            "file": self.file_name,
                            "tag": tag["tag"],
                            "attributes": tag["attributes"],
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
    def __init__(self, file_name: str, file_content: str, all_files: Dict[str, str]):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.function_definitions: List[Dict[str, Any]] = []
        self.function_calls: Dict[str, List[Dict[str, Any]]] = {}
        self.arrow_functions: List[Dict[str, Any]] = []
        self.comments: List[Dict[str, Any]] = []

    def parse(self) -> None:
        self._parse_function_definitions()
        self._parse_arrow_functions()
        self._parse_function_calls()
        self._parse_comments()

    def _parse_function_definitions(self) -> None:
        for func in re.findall(r"function\s+(\w+)\s*\(", self.file_content):
            self.function_definitions.append({"name": func})

    def _parse_arrow_functions(self) -> None:
        for func in re.findall(r"(\w+)\s*=\s*\(\s*[^)]*\)\s*=>", self.file_content):
            self.arrow_functions.append({"name": func})

    def _parse_function_calls(self) -> None:
        for call in re.findall(r"(\w+)\s*\(", self.file_content):
            self.function_calls.setdefault(call, []).append({"file": self.file_name})

    def _parse_comments(self) -> None:
        for match in re.finditer(r"//(.*)", self.file_content):
            line = self.file_content.count("\n", 0, match.start()) + 1
            self.comments.append({"line": line, "comment": match.group(1).strip()})
        for match in re.finditer(r"/\*.*?\*/", self.file_content, re.DOTALL):
            line = self.file_content.count("\n", 0, match.start()) + 1
            self.comments.append({"line": line, "comment": match.group(0).strip()})

    def get_js_relations(self) -> Dict[str, Any]:
        return {
            "defined": self.function_definitions,
            "arrow_functions": self.arrow_functions,
            "called": self.function_calls,
            "comments": self.comments,
        }


# ---------- Convenience facade for Django views/services ----------

def parse_code(language: str, file_name: str, file_content: str, all_files: Dict[str, str] | None = None) -> Dict[str, Any]:
    """
    language: 'python' | 'c' | 'css' | 'html' | 'js'
    all_files: optional mapping filename -> content for cross-file cases
    """
    lang = (language or "").strip().lower()
    all_files = all_files or {}

    if lang == "python":
        parser = PythonParser(file_name, file_content)
        parser.parse()
        return parser.get_python_relations()
    if lang == "c":
        parser = CParser(file_name, file_content, all_files)
        parser.parse()
        return parser.get_c_relations()
    if lang == "css":
        parser = CssParser(file_name, file_content, all_files)
        parser.parse()
        return parser.get_css_relations()
    if lang == "html":
        parser = HtmlParser(file_name, file_content, all_files)
        # Build CSS parsers if provided in all_files
        css_parsers: List[CssParser] = []
        for name, content in all_files.items():
            if name.lower().endswith(".css"):
                cp = CssParser(name, content, all_files)
                cp.parse()
                css_parsers.append(cp)
        parser.parse(css_parsers)
        return parser.get_html_relations()
    if lang in ("js", "javascript"):
        parser = JsParser(file_name, file_content, all_files)
        parser.parse()
        return parser.get_js_relations()

    raise ValueError(f"Unsupported language: {language}")

