#!/usr/bin/env python3
"""Validate the canonical static progress page and safe manifest wiring."""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "progress"
REQUIRED_IDS = {
    "page-title", "checkpoint", "checkpoint-explanation", "network-status",
    "last-updated", "range-count", "verified-count", "contributor-count",
    "history-empty", "history-list", "source-commit",
}
ELEMENT_IDS = re.compile(r'''\bel\(\s*["']([^"']+)["']\s*\)''')


class Inspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"] or "")
        if tag == "link" and values.get("href") and "stylesheet" in (values.get("rel") or "").lower().split():
            self.assets.append(values["href"] or "")


def fail(message: str) -> None:
    raise ValueError(message)


def validate() -> None:
    required_files = (SITE / "index.html", SITE / "app.js", SITE / "styles.css")
    for path in required_files:
        if not path.is_file():
            fail(f"missing progress-site file: {path.relative_to(ROOT)}")
    parser = Inspector()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    parser.close()
    duplicates = sorted({element_id for element_id in parser.ids if parser.ids.count(element_id) > 1})
    if duplicates:
        fail("duplicate HTML IDs: " + ", ".join(duplicates))
    missing = sorted(REQUIRED_IDS - set(parser.ids))
    if missing:
        fail("progress page is missing required IDs: " + ", ".join(missing))
    site_root = SITE.resolve()
    for asset in parser.assets:
        parsed = urlparse(asset)
        if parsed.scheme or parsed.netloc or asset.startswith(("#", "data:")):
            continue
        resolved = (SITE / parsed.path).resolve()
        if resolved != site_root and site_root not in resolved.parents:
            fail(f"progress asset escapes its folder: {asset}")
        if not resolved.is_file():
            fail(f"missing local progress asset: {asset}")
    script = (SITE / "app.js").read_text(encoding="utf-8")
    missing_hooks = sorted(set(ELEMENT_IDS.findall(script)) - set(parser.ids))
    if missing_hooks:
        fail("JavaScript references missing HTML IDs: " + ", ".join(missing_hooks))
    if "eval(" in script or "innerHTML" in script:
        fail("progress page must not execute imported content or insert it as HTML")
    for required in (
        'cache: "no-store"',
        "textContent",
        "global_manifest.json",
        "raw.githubusercontent.com/${REPOSITORY}/${currentManifestCommit}/",
        "validateRecordFile",
    ):
        if required not in script:
            fail(f"progress page is missing safe canonical network behavior: {required}")
    if not (SITE / "styles.css").read_text(encoding="utf-8").strip():
        fail("progress stylesheet is empty")
    print(f"Progress site valid: HTML IDs={len(parser.ids)}, local assets={len(parser.assets)}, DOM hooks={len(set(ELEMENT_IDS.findall(script)))}")


if __name__ == "__main__":
    try:
        validate()
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"Progress site validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
