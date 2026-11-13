#!/usr/bin/env python3
"""Build static dashboard data from the validated repository records."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checkpoint = json.loads((root / "global" / "checkpoint.json").read_text(encoding="utf-8"))
    records_dir = root / "records"
    summaries = []
    contributors: Counter[str] = Counter()
    total_entries = 0
    verified_entries = 0

    for path in sorted(records_dir.glob("*.json")) if records_dir.exists() else []:
        record = json.loads(path.read_text(encoding="utf-8"))
        entries = record["entries"]
        total_entries += len(entries)
        verified_entries += sum(entry["status"] == "arb_verified" for entry in entries)
        contributors[record["contributor"]["display_name"]] += 1
        summaries.append({
            "record_id": record["record_id"],
            "created_utc": record["created_utc"],
            "contributor": record["contributor"]["display_name"],
            "start_index": record["start_index"],
            "end_index": record["end_index"],
            "entry_count": len(entries),
            "verified_count": sum(entry["status"] == "arb_verified" for entry in entries)
        })

    summaries.sort(key=lambda item: item["created_utc"], reverse=True)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checkpoint": checkpoint,
        "record_count": len(summaries),
        "entry_count": total_entries,
        "arb_verified_entry_count": verified_entries,
        "contributor_count": len(contributors),
        "contributors": [{"display_name": name, "record_count": count}
                         for name, count in sorted(contributors.items())],
        "recent_records": summaries[:20]
    }
    output = root / "website" / "data" / "index.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output.relative_to(root)} ({len(summaries)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
