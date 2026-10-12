"""Writes the comparison result as one self-contained HTML file."""
import datetime
import json
import re
from pathlib import Path

FOLDER = "SiebDiff Reports"


def _target_dirs():
    yield Path.home() / "Documents" / FOLDER
    yield Path.home() / FOLDER


def render(web_dir, result):
    template = (web_dir / "report_template.html").read_text(encoding="utf-8")
    engine = (web_dir / "diff.js").read_text(encoding="utf-8")
    # "</" inside the embedded data or script must not end the surrounding <script> block.
    data = json.dumps(result, default=str).replace("</", "<\\/").replace("<!--", "<\\u0021--")
    return (template
            .replace("/*DIFF_ENGINE*/", engine.replace("</", "<\\/"))
            .replace("/*REPORT_DATA*/", data))


def save(web_dir, result, label=""):
    html = render(web_dir, result)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    label = re.sub(r"[^\w\-]+", "_", label).strip("_")[:60]
    name = f"SiebDiff_{label}_{stamp}.html" if label else f"SiebDiff_{stamp}.html"
    error = None
    for folder in _target_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            path.write_text(html, encoding="utf-8")
            return path
        except OSError as exc:
            error = exc
    raise error
