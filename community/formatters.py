# community/formatters.py
from __future__ import annotations
from typing import Tuple

# Lazy imports so the app runs even if tools aren't installed
try:
    import black
except Exception:  # pragma: no cover
    black = None

MAX_FORMAT_BYTES = 1_000_000  # 1 MB safety cap

def _is(path: str, *exts: str) -> bool:
    p = (path or "").lower()
    return any(p.endswith(e) for e in exts)

def format_for_path(path: str, content: str) -> Tuple[str, str | None]:
    """
    Returns (formatted_content, tool_name or None).
    Never raises; returns original content on any error.
    """
    if not isinstance(content, str):
        return content, None
    if len(content.encode("utf-8", "ignore")) > MAX_FORMAT_BYTES:
        # too large to format safely
        return content, None

    # Python -> Black (if available)
    if _is(path, ".py"):
        if black is None:
            return content, None
        try:
            mode = black.FileMode()  # defaults: PEP8 line length 88
            formatted = black.format_str(content, mode=mode)
            return formatted, "black"
        except Exception:
            return content, None

    # TODO: add more languages later (Prettier for js/ts/html/css via a worker, clang-format for C, etc.)

    return content, None
