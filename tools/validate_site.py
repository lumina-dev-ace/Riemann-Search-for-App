#!/usr/bin/env python3
"""Validate the static dashboard's local assets, DOM hooks, and data file."""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "website"
REQUIRED_IDS = {
    "status-dot", "network-status", "checkpoint-value", "checkpoint-note",
    "updated-at", "record-count", "entry-count", "verified-count",
    "contributor-count", "records-list",
}
BY_ID_PATTERN = re.compile(r"""\bbyId\(\s*["']([^"']+)["']\s*\)""")


class SiteError(Exception):
    """Raised when the static dashboard is structurally invalid."""


class DocumentInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.local_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.append(element_id)
        if tag == "script" and values.get("src"):
            self.local_assets.append(values["src"] or "")
        if tag == "link" and values.get("href"):
            rel = (values.get("rel") or "").lower().split()
            if "stylesheet" in rel:
                self.local_assets.append(values["href"] or "")


def fail(message: str) -> None:
    raise SiteError(message)


def validate_site() -> list[str]:
    required_files = (
        SITE / "index.html",
        SITE / "app.js",
        SITE / "styles.css",
        SITE / "data" / "index.json",
    )
    for path in required_files:
        if not path.is_file():
            fail(f"missing required dashboard file: {path.relative_to(ROOT)}")

    parser = DocumentInspector()
    try:
        parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
        parser.close()
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        fail(f"cannot parse website/index.html: {exc}")

    duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    if duplicates:
        fail("duplicate HTML IDs: " + ", ".join(duplicates))

    missing_ids = sorted(REQUIRED_IDS - set(parser.ids))
    if missing_ids:
        fail("dashboard HTML is missing required IDs: " + ", ".join(missing_ids))

    site_root = SITE.resolve()
    for asset in parser.local_assets:
        parsed = urlparse(asset)
        if parsed.scheme or parsed.netloc or asset.startswith(("#", "data:")):
            continue
        asset_path = (SITE / parsed.path).resolve()
        if asset_path != site_root and site_root not in asset_path.parents:
            fail(f"dashboard asset escapes website directory: {asset}")
        if not asset_path.is_file():
            fail(f"dashboard local asset does not exist: {asset}")

    javascript = (SITE / "app.js").read_text(encoding="utf-8")
    referenced_ids = set(BY_ID_PATTERN.findall(javascript))
    missing_hooks = sorted(referenced_ids - set(parser.ids))
    if missing_hooks:
        fail("JavaScript references missing HTML IDs: " + ", ".join(missing_hooks))

    try:
        payload = json.loads((SITE / "data" / "index.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid website/data/index.json: {exc}")

    required_keys = {
        "generated_utc", "checkpoint", "record_count", "entry_count",
        "arb_verified_entry_count", "contributor_count", "contributors",
        "recent_records",
    }
    if not isinstance(payload, dict) or not required_keys.issubset(payload):
        fail("dashboard data is missing required top-level fields")

    checkpoint = payload["checkpoint"]
    if not isinstance(checkpoint, dict):
        fail("dashboard checkpoint must be an object")
    if checkpoint.get("status") == "uninitialized":
        if checkpoint.get("highest_verified_index") is not None:
            fail("uninitialized dashboard checkpoint must not contain a completed index")
    elif checkpoint.get("status") == "initialized":
        high = checkpoint.get("highest_verified_index")
        if isinstance(high, bool) or not isinstance(high, int) or high < 1:
            fail("initialized dashboard checkpoint must contain a positive integer")
    else:
        fail("dashboard checkpoint status is not recognized")

    for key in ("record_count", "entry_count", "arb_verified_entry_count", "contributor_count"):
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            fail(f"dashboard {key} must be a non-negative integer")
    if not isinstance(payload["contributors"], list) or not isinstance(payload["recent_records"], list):
        fail("dashboard contributors and recent_records must be arrays")

    return [
        f"HTML IDs: {len(parser.ids)}",
        f"Local assets: {len(parser.local_assets)}",
        f"JavaScript DOM hooks: {len(referenced_ids)}",
        f"Research records in dashboard: {payload['record_count']}",
    ]


def main() -> int:
    try:
        details = validate_site()
    except SiteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("RiemannSearch dashboard: VALID")
    for detail in details:
        print(detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
