from __future__ import annotations

import base64
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "zeabur-backend" / "app.py"
STATIC_FILES = [
    ("/", "index.html", "text/html; charset=utf-8"),
    ("/index.html", "index.html", "text/html; charset=utf-8"),
    (
        "/calculator-original.html",
        "calculator-original.html",
        "text/html; charset=utf-8",
    ),
    (
        "/assets/chart.umd.min.js",
        "assets/chart.umd.min.js",
        "text/javascript; charset=utf-8",
    ),
    (
        "/assets/mathjax/tex-svg.js",
        "assets/mathjax/tex-svg.js",
        "text/javascript; charset=utf-8",
    ),
]


def build_embedded_block() -> str:
    lines = ["EMBEDDED_STATIC_FILES = {"]
    for route, relative_path, content_type in STATIC_FILES:
        raw = (ROOT / relative_path).read_bytes()
        encoded = base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")
        lines.append(f"    {route!r}: ({content_type!r}, {encoded!r}),")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    source = BACKEND.read_text(encoding="utf-8")
    start = source.index("EMBEDDED_STATIC_FILES = {")
    end = source.index("\n\n\ndef static_response_for", start)
    updated = source[:start] + build_embedded_block() + source[end:]
    BACKEND.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
