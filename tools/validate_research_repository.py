#!/usr/bin/env python3
"""Offline integrity and consecutive-coverage validator; standard library only."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 10**37
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
VERIFIED = {"verified", "certified_interval_rechecked"}


def fail(message: str) -> None:
    raise ValueError(message)


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f"duplicate JSON key {key} in {path.relative_to(ROOT)}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=lambda value: fail(f"invalid constant {value}"))


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def verify_hash(document, label: str) -> None:
    integrity = document.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        fail(f"{label} has no SHA-256 integrity metadata")
    supplied = integrity.get("sha256")
    payload = dict(document)
    payload.pop("integrity", None)
    actual = hashlib.sha256(canonical(payload)).hexdigest()
    if supplied != actual:
        fail(f"{label} integrity mismatch (expected canonical digest {actual})")


def index(value, label: str) -> int:
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        fail(f"{label} must be an exact canonical decimal string")
    number = int(value)
    if number < 1 or number >= LIMIT:
        fail(f"{label} is outside the supported FLINT range n < 10^37")
    return number


def validate_record(path: Path, reference: dict) -> tuple[int, int]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        fail(f"record file SHA-256 mismatch: {path.relative_to(ROOT)}")
    record = read_json(path)
    verify_hash(record, f"record {path.name}")
    if record.get("schema_version") != 1 or record.get("record_type") != "riemannsearch-zero-range":
        fail(f"unsupported research record schema: {path.name}")
    computation = record.get("computation") or {}
    verification = record.get("verification") or {}
    if "flint" not in str(computation.get("backend", "")).casefold() and "arb" not in str(computation.get("backend", "")).casefold():
        fail(f"record is not from the FLINT/Arb backend: {path.name}")
    if "arb" not in str(verification.get("method", "")).casefold():
        fail(f"record has no Arb verification method: {path.name}")
    results = record.get("results")
    if not isinstance(results, list) or not results:
        fail(f"record has no results: {path.name}")
    expected = index(record.get("start_index"), "record start_index")
    first = expected
    statuses = set()
    intervals = []
    for result in results:
        item_index = index(result.get("zero_index"), "result zero_index")
        if item_index != expected:
            fail(f"record has a missing or duplicated result index before {item_index}: {path.name}")
        expected += 1
        for field in ("real_part", "imag_part", "residual", "verification_residual", "computed_at"):
            if not isinstance(result.get(field), str) or not result[field]:
                fail(f"result {item_index} is missing {field}: {path.name}")
        if result.get("verification_status") not in VERIFIED or "arb" not in str(result.get("verification_method", "")).casefold():
            fail(f"result {item_index} is not Arb-rechecked: {path.name}")
        statuses.add(result["verification_status"])
        intervals.append(bool(result.get("certified_interval")))
        if type(result.get("precision_digits")) is not int or result["precision_digits"] < 2:
            fail(f"result {item_index} has invalid computation precision")
        if type(result.get("verification_precision_digits")) is not int or result["verification_precision_digits"] < 2:
            fail(f"result {item_index} has invalid verification precision")
        if result.get("certified_interval") and not (result.get("real_enclosure") and result.get("imag_enclosure")):
            fail(f"result {item_index} claims an interval without both enclosures")
        for timing_field in ("computation_time_ms", "verification_time_ms"):
            timing = result.get(timing_field)
            if timing is not None and (not isinstance(timing, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", timing)):
                fail(f"result {item_index} has invalid {timing_field}; use a decimal string or null")
    last = expected - 1
    if last != index(record.get("end_index"), "record end_index"):
        fail(f"record endpoint does not derive from its final result: {path.name}")
    if len(statuses) != 1 or verification.get("status") not in statuses:
        fail(f"record mixes or misstates verification statuses: {path.name}")
    if verification.get("interval_verification") is not all(intervals):
        fail(f"record interval flag does not match its results: {path.name}")
    if record.get("contributor_id") != reference.get("contributor_id"):
        fail(f"contributor metadata mismatch: {path.name}")
    if first != index(reference.get("start_index"), "manifest range start") or last != index(reference.get("end_index"), "manifest range end"):
        fail(f"manifest range endpoints mismatch: {path.name}")
    return first, last


def validate() -> None:
    manifest_path = ROOT / "data" / "global_manifest.json"
    manifest = read_json(manifest_path)
    verify_hash(manifest, "global manifest")
    if manifest.get("schema_version") != 1 or manifest.get("network_id") != "riemannsearch-global-research":
        fail("unsupported global manifest schema or network ID")
    ranges = manifest.get("accepted_ranges")
    history = manifest.get("publication_history")
    if not isinstance(ranges, list) or not isinstance(history, list):
        fail("range and publication history must be arrays")
    if manifest.get("status") == "uninitialized":
        if manifest.get("first_required_index") is not None or manifest.get("global_checkpoint_index") is not None or ranges or history:
            fail("uninitialized manifest must not claim progress")
        print("Research network awaiting initialization.")
        return
    if manifest.get("status") != "initialized":
        fail("manifest status must be initialized or uninitialized")
    cursor = index(manifest.get("first_required_index"), "first_required_index")
    paths = set()
    for position, reference in enumerate(ranges, start=1):
        start, end = index(reference.get("start_index"), "range start"), index(reference.get("end_index"), "range end")
        path = reference.get("record_path")
        if not isinstance(path, str) or not path.startswith("data/ranges/") or ".." in Path(path).parts:
            fail(f"unsafe record path in range {position}")
        if path in paths:
            fail(f"duplicate range record reference: {path}")
        paths.add(path)
        if start != cursor or end < start:
            fail(f"gap or overlap before range {position}; expected {cursor}, got {start}")
        record_start, record_end = validate_record(ROOT / Path(path), reference)
        if (record_start, record_end) != (start, end):
            fail(f"record endpoint mismatch: {path}")
        cursor = end + 1
    checkpoint = str(cursor - 1) if ranges else None
    if manifest.get("global_checkpoint_index") != checkpoint:
        fail("checkpoint is not the end of the accepted consecutive coverage")
    if len(history) < len(ranges):
        fail("publication history does not cover each accepted range")
    print(f"Manifest valid: status={manifest['status']}, accepted_ranges={len(ranges)}, global_checkpoint={checkpoint or 'none'}")


if __name__ == "__main__":
    try:
        validate()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Research repository validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
