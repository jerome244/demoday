# community/linters.py
from __future__ import annotations
from typing import List, Dict

# LSP-like positions are 0-based (line & character)
def _diag(line0: int, col0: int, line1: int, col1: int, message: str, severity: str, source: str) -> Dict:
    return {
        "range": {"start": {"line": line0, "character": col0}, "end": {"line": line1, "character": col1}},
        "message": message,
        "severity": severity,  # "error" | "warning" | "info"
        "source": source,
    }

def _balance_check(text: str, pairs: dict[str, str], source: str) -> List[Dict]:
    """Generic bracket/brace balancing diagnostics for JS/CSS/HTML fallbacks."""
    openers = set(pairs.keys())
    closers = set(pairs.values())
    stack: list[tuple[str, int, int]] = []  # (char, line, col)
    diags: List[Dict] = []
    line, col = 0, 0
    in_str = None
    esc = False

    for ch in text:
        if ch == "\n":
            line += 1
            col = 0
        else:
            col += 1

        # very light string handling to not flag braces inside quotes too much
        if in_str:
            if not esc and ch == in_str:
                in_str = None
            esc = (ch == "\\" and not esc)
            continue
        if ch in ('"', "'"):
            in_str = ch
            esc = False
            continue

        if ch in openers:
            stack.append((ch, line, col))
        elif ch in closers:
            if not stack:
                diags.append(_diag(line, max(col - 1, 0), line, col, f"Unmatched '{ch}'", "error", source))
            else:
                top, tl, tc = stack[-1][0], stack[-1][1], stack[-1][2]
                if pairs.get(top) == ch:
                    stack.pop()
                else:
                    diags.append(_diag(line, max(col - 1, 0), line, col, f"Mismatched '{top}' vs '{ch}'", "error", source))

    # any unclosed
    for opener, l, c in stack:
        diags.append(_diag(l, max(c - 1, 0), l, c, f"Unclosed '{opener}'", "error", source))
    return diags

def lint_python(path: str, content: str) -> List[Dict]:
    diags: List[Dict] = []
    # True syntax check
    try:
        compile(content, path or "<string>", "exec")
    except SyntaxError as e:
        l0 = max((getattr(e, "lineno", 1) or 1) - 1, 0)
        c0 = max((getattr(e, "offset", 1) or 1) - 1, 0)
        l1 = max((getattr(e, "end_lineno", getattr(e, "lineno", 1)) or 1) - 1, 0)
        c1 = max((getattr(e, "end_offset", getattr(e, "offset", 1)) or 1) - 1, 0)
        diags.append(_diag(l0, c0, l1, c1, e.msg, "error", "python"))
    return diags

def lint_js(path: str, content: str) -> List[Dict]:
    # Lightweight structural check (braces/parens/brackets)
    return _balance_check(content, {"{": "}", "(": ")", "[": "]"}, "js")

def lint_css(path: str, content: str) -> List[Dict]:
    # Basic: ensure braces are balanced; catch obvious mistakes
    return _balance_check(content, {"{": "}"}, "css")

def lint_html(path: str, content: str) -> List[Dict]:
    # Very light: angle brackets balance check
    return _balance_check(content, {"<": ">"}, "html")

def lint_for_path(path: str, content: str) -> List[Dict]:
    p = (path or "").lower()
    if p.endswith(".py"):   return lint_python(path, content)
    if p.endswith(".js"):   return lint_js(path, content)
    if p.endswith(".css"):  return lint_css(path, content)
    if p.endswith(".html") or p.endswith(".htm"): return lint_html(path, content)
    # add more: ts/tsx/vue/json/yaml/c/…
    return []
