"""Regenerate docs/executive-summary.txt and .html from docs/executive-summary.md.

The Markdown file is the only source. This script understands the small subset
the summary uses: one H1, H2 sections, paragraphs, one pipe table, bullet lists
and inline code. It needs only the standard library:

    python docs/build_summary.py

The PDF is printed from the generated HTML with Microsoft Edge (headless):

    msedge --headless --no-pdf-header-footer \
        --print-to-pdf=docs/executive-summary.pdf docs/executive-summary.html
"""

from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path

DOCS = Path(__file__).resolve().parent
SOURCE = DOCS / "executive-summary.md"
WIDTH = 78

CSS = """\
@page { size: A4; margin: 12mm 13mm; }
* { box-sizing: border-box; }
html { background: #ffffff; }
body { margin: 0; font-family: "Segoe UI", system-ui, sans-serif; color: #1c2733;
       font-size: 9.2pt; line-height: 1.38; background: #ffffff; }
h1 { font-size: 16pt; margin: 0 0 4px; padding-bottom: 5px; border-bottom: 3px solid #118d57; }
h2 { font-size: 9.6pt; text-transform: uppercase; letter-spacing: 0.7px; color: #0c6b3d;
     margin: 12px 0 4px; }
p { margin: 0 0 5px; }
h1 + p { color: #3d4b5a; font-weight: 600; margin-top: 6px; }
h1 + p + p { color: #5b6b7b; font-size: 8.4pt; }
ul { margin: 0 0 4px; padding-left: 16px; }
li { margin-bottom: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 8.3pt; margin-top: 4px; }
th { background: #0f1c2e; color: #ffffff; text-align: left; padding: 4px 6px; font-size: 8pt; }
td { border-bottom: 1px solid #dde4ee; padding: 5px 6px; vertical-align: top; }
td:first-child { font-weight: 600; width: 27mm; }
code { font-family: Consolas, monospace; font-size: 0.95em; background: #f0f3f7;
       padding: 0 2px; border-radius: 2px; }
"""

PLAIN = {"·": "|", "→": "->", "–": "-", "—": "-", "≈": "~", "≤": "<=", "≠": "!="}


def parse(text: str) -> list[tuple[str, object]]:
    """Split the Markdown into (kind, payload) blocks."""
    blocks: list[tuple[str, object]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
            i += 1
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows))
        elif line.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].strip():
                if lines[i].startswith("- "):
                    items.append(lines[i][2:].strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            blocks.append(("ul", items))
        else:
            para = []
            while i < len(lines) and lines[i].strip():
                para.append(lines[i])
                i += 1
            blocks.append(("p", para))
    return blocks


def inline_html(text: str) -> str:
    parts = text.split("`")
    out = []
    for n, part in enumerate(parts):
        escaped = html.escape(part, quote=False)
        out.append(f"<code>{escaped}</code>" if n % 2 else escaped)
    return "".join(out)


def to_html(blocks: list[tuple[str, object]]) -> str:
    title = next(str(p) for k, p in blocks if k == "h1").split(":")[0]
    out = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title>",
        (
            "<!-- Generated from docs/executive-summary.md by docs/build_summary.py;"
            " edit the .md and regenerate. -->"
        ),
        "<style>",
        CSS.rstrip("\n"),
        "</style>",
        "</head>",
        "<body>",
    ]
    for kind, payload in blocks:
        if kind in ("h1", "h2"):
            out.append(f"<{kind}>{inline_html(str(payload))}</{kind}>")
        elif kind == "p":
            out.append("<p>" + "\n".join(inline_html(ln) for ln in payload) + "</p>")  # type: ignore[union-attr]
        elif kind == "ul":
            out.append("<ul>")
            out += [f"<li>{inline_html(item)}</li>" for item in payload]  # type: ignore[union-attr]
            out.append("</ul>")
        elif kind == "table":
            header, *rows = payload  # type: ignore[misc]
            out += ["<table>", "<thead>", "<tr>"]
            out += [f"<th>{inline_html(c)}</th>" for c in header]
            out += ["</tr>", "</thead>", "<tbody>"]
            for row in rows:
                out.append("<tr>")
                out += [f"<td>{inline_html(c)}</td>" for c in row]
                out.append("</tr>")
            out += ["</tbody>", "</table>"]
    out += ["</body>", "</html>"]
    return "\n".join(out) + "\n"


def wrap(text: str, width: int, **kwargs: str) -> list[str]:
    return textwrap.wrap(text, width, break_on_hyphens=False, **kwargs)  # type: ignore[misc]


def plain(text: str) -> str:
    text = text.replace("`", "")
    for src, dst in PLAIN.items():
        text = text.replace(src, dst)
    return text


def heading(text: str, rule: str) -> list[str]:
    text = plain(text).upper()
    return [text, rule * len(text), ""]


def to_txt(blocks: list[tuple[str, object]]) -> str:
    out: list[str] = []
    for kind, payload in blocks:
        if kind == "h1":
            out += heading(str(payload), "=")
        elif kind == "h2":
            out += heading(str(payload), "-")
        elif kind == "p":
            joined = " ".join(ln.strip() for ln in payload)  # type: ignore[union-attr]
            out += wrap(plain(joined), WIDTH) + [""]
        elif kind == "ul":
            for item in payload:  # type: ignore[union-attr]
                out += wrap(
                    plain(item), WIDTH, initial_indent="- ", subsequent_indent="  "
                )
            out.append("")
        elif kind == "table":
            header, *rows = payload  # type: ignore[misc]
            for n, row in enumerate(rows, start=1):
                out += wrap(
                    f"{n}) {plain(row[0]).upper()}", WIDTH, subsequent_indent="   "
                )
                for label, cell in zip(header[1:], row[1:]):
                    out += wrap(
                        f"{plain(label)}: {plain(cell)}",
                        WIDTH,
                        initial_indent="   ",
                        subsequent_indent="   ",
                    )
                out.append("")
    out += wrap(
        "(Generated from docs/executive-summary.md by docs/build_summary.py: "
        "plain-text version for email and ATS attachments.)",
        WIDTH,
    )
    return "\n".join(out) + "\n"


def main() -> None:
    blocks = parse(SOURCE.read_text(encoding="utf-8"))
    (DOCS / "executive-summary.html").write_text(
        to_html(blocks), encoding="utf-8", newline="\n"
    )
    (DOCS / "executive-summary.txt").write_text(
        to_txt(blocks), encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
