#!/usr/bin/env python3
"""Validate the public RiemannSearch research-network data (stdlib only)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{path}: cannot read valid JSON ({exc})")


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_timestamp(value: Any, where: str) -> None:
    if not isinstance(value, str):
        fail(f"{where}: expected ISO-8601 timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"{where}: invalid ISO-8601 timestamp")


def decimal_value(value: Any, where: str) -> Decimal:
    if not isinstance(value, str):
        fail(f"{where}: interval endpoints must be decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation:
        fail(f"{where}: invalid decimal value {value!r}")
    if not number.is_finite():
        fail(f"{where}: interval endpoints must be finite")
    return number


def validate_checkpoint(checkpoint: Any) -> None:
    required = {
        "schema_version", "status", "highest_verified_index", "updated_utc",
        "source_commit", "record_count", "note",
    }
    if not isinstance(checkpoint, dict) or set(checkpoint) != required:
        fail("global/checkpoint.json: missing or unexpected fields")
    if checkpoint["schema_version"] != 1:
        fail("checkpoint: unsupported schema_version")
    if checkpoint["status"] not in ("uninitialized", "initialized"):
        fail("checkpoint: status must be uninitialized or initialized")
    high = checkpoint["highest_verified_index"]
    if checkpoint["status"] == "uninitialized":
        if high is not None:
            fail("uninitialized checkpoint must have highest_verified_index=null")
        if checkpoint["updated_utc"] is not None or checkpoint["source_commit"] is not None:
            fail("uninitialized checkpoint cannot claim an update timestamp or source commit")
    else:
        if not is_int(high) or high < 1:
            fail("initialized checkpoint must have a positive integer highest_verified_index")
        check_timestamp(checkpoint["updated_utc"], "checkpoint.updated_utc")
        if not isinstance(checkpoint["source_commit"], str) or len(checkpoint["source_commit"]) < 7:
            fail("initialized checkpoint must identify its source commit")
    if not is_int(checkpoint["record_count"]) or checkpoint["record_count"] < 0:
        fail("checkpoint.record_count must be a non-negative integer")
    if not isinstance(checkpoint["note"], str):
        fail("checkpoint.note must be text")


def validate_record(record: Any, path: Path) -> list[dict[str, Any]]:
    where = str(path)
    required = {
        "schema_version", "record_id", "created_utc", "contributor", "app_version",
        "numerical_backend", "precision_bits", "start_index", "end_index", "entries",
    }
    if not isinstance(record, dict) or set(record) != required:
        fail(f"{where}: missing or unexpected top-level fields")
    if record["schema_version"] != 1:
        fail(f"{where}: unsupported schema_version")
    record_id = record["record_id"]
    if not isinstance(record_id, str) or not record_id or len(record_id) > 120:
        fail(f"{where}: invalid record_id")
    check_timestamp(record["created_utc"], f"{where}.created_utc")
    contributor = record["contributor"]
    if not isinstance(contributor, dict) or set(contributor) != {"display_name"}:
        fail(f"{where}: contributor must contain only display_name")
    if not isinstance(contributor["display_name"], str) or not contributor["display_name"].strip():
        fail(f"{where}: contributor.display_name must be non-empty")
    if not isinstance(record["app_version"], str) or not record["app_version"]:
        fail(f"{where}: app_version must be non-empty text")
    if record["numerical_backend"] != "FLINT/Arb":
        fail(f"{where}: numerical_backend must be FLINT/Arb")
    precision = record["precision_bits"]
    if not is_int(precision) or precision < 32:
        fail(f"{where}: precision_bits must be an integer >= 32")
    start, end = record["start_index"], record["end_index"]
    if not is_int(start) or not is_int(end) or start < 1 or end < start:
        fail(f"{where}: invalid inclusive index range")
    entries = record["entries"]
    if not isinstance(entries, list) or len(entries) != end - start + 1:
        fail(f"{where}: entries must contain exactly one row for every index in the range")

    for offset, entry in enumerate(entries):
        item_where = f"{where}.entries[{offset}]"
        item_fields = {"index", "status", "ordinate_interval", "verification"}
        if not isinstance(entry, dict) or set(entry) != item_fields:
            fail(f"{item_where}: missing or unexpected fields")
        expected_index = start + offset
        if not is_int(entry["index"]) or entry["index"] != expected_index:
            fail(f"{item_where}: index must equal expected contiguous index {expected_index}")
        if entry["status"] not in ("candidate", "evaluated", "arb_verified"):
            fail(f"{item_where}: invalid status")
        interval = entry["ordinate_interval"]
        if not isinstance(interval, list) or len(interval) != 2:
            fail(f"{item_where}: ordinate_interval must contain [lower, upper]")
        lower = decimal_value(interval[0], item_where + ".ordinate_interval[0]")
        upper = decimal_value(interval[1], item_where + ".ordinate_interval[1]")
        if lower > upper:
            fail(f"{item_where}: interval lower endpoint exceeds upper endpoint")
        verification = entry["verification"]
        verify_fields = {"method", "backend", "certified", "precision_bits"}
        if not isinstance(verification, dict) or set(verification) != verify_fields:
            fail(f"{item_where}: invalid verification object")
        if not isinstance(verification["certified"], bool):
            fail(f"{item_where}: verification.certified must be boolean")
        vbits = verification["precision_bits"]
        if not is_int(vbits) or vbits < 0:
            fail(f"{item_where}: verification.precision_bits must be non-negative")
        if entry["status"] == "arb_verified":
            if verification["method"] != "arb_interval" or verification["backend"] != "FLINT/Arb":
                fail(f"{item_where}: arb_verified requires Arb interval verification")
            if verification["certified"] is not True or vbits < 32:
                fail(f"{item_where}: arb_verified requires certified=true and precision_bits >= 32")
        else:
            if verification["certified"] is True:
                fail(f"{item_where}: non-verified entries cannot claim certified=true")
    if entries[0]["index"] != start or entries[-1]["index"] != end:
        fail(f"{where}: entry indices do not match declared range")
    return entries


def validate_network(root: Path) -> dict[str, Any]:
    checkpoint_path = root / "global" / "checkpoint.json"
    checkpoint = read_json(checkpoint_path)
    validate_checkpoint(checkpoint)

    records_dir = root / "records"
    record_paths = sorted(records_dir.glob("*.json")) if records_dir.exists() else []
    index_map: dict[int, dict[str, Any]] = {}
    record_ids: set[str] = set()
    contributors: set[str] = set()

    for path in record_paths:
        record = read_json(path)
        entries = validate_record(record, path)
        if record["record_id"] in record_ids:
            fail(f"duplicate record_id: {record['record_id']}")
        record_ids.add(record["record_id"])
        contributors.add(record["contributor"]["display_name"])
        for entry in entries:
            index = entry["index"]
            if index in index_map:
                fail(f"duplicate research index {index} across records")
            index_map[index] = entry

    if checkpoint["status"] == "initialized":
        high = checkpoint["highest_verified_index"]
        if checkpoint["record_count"] != len(record_paths):
            fail("checkpoint.record_count does not match records/*.json")
        present = sorted(index for index in index_map if index <= high)
        if len(present) != high:
            fail(f"checkpoint claims indices 1..{high}, but only {len(present)} distinct indices exist in that range")
        for expected, actual in enumerate(present, start=1):
            if actual != expected:
                fail(f"checkpoint sequence gap: expected index {expected}, found {actual}")
            if index_map[actual]["status"] != "arb_verified":
                fail(f"checkpoint includes index {actual} that is not Arb-verified")

    return {
        "status": checkpoint["status"],
        "highest_verified_index": checkpoint["highest_verified_index"],
        "record_files": len(record_paths),
        "entry_count": len(index_map),
        "contributors": len(contributors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        summary = validate_network(args.root.resolve())
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("RiemannSearch research network: VALID")
    print(f"Checkpoint status: {summary['status']}")
    if summary["status"] == "uninitialized":
        print("Global verified checkpoint: not initialized")
    else:
        print(f"Global verified checkpoint: {summary['highest_verified_index']}")
    print(f"Record files: {summary['record_files']}")
    print(f"Entry rows: {summary['entry_count']}")
    print(f"Contributors: {summary['contributors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
