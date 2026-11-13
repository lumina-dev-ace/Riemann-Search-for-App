"""Tests for the public-network structural validator."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_network import ValidationError, validate_network


def base_record() -> dict:
    return {
        "schema_version": 1,
        "record_id": "sample-001",
        "created_utc": "2026-11-13T12:00:00Z",
        "contributor": {"display_name": "Example contributor"},
        "app_version": "0.0-test",
        "numerical_backend": "FLINT/Arb",
        "precision_bits": 128,
        "start_index": 1,
        "end_index": 2,
        "entries": [
            {
                "index": index,
                "status": "arb_verified",
                "ordinate_interval": [str(index) + ".0", str(index) + ".1"],
                "verification": {
                    "method": "arb_interval",
                    "backend": "FLINT/Arb",
                    "certified": True,
                    "precision_bits": 128
                }
            }
            for index in (1, 2)
        ]
    }


class NetworkValidatorTests(unittest.TestCase):
    def make_root(self, checkpoint: dict | None = None, records: list[dict] | None = None) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "global").mkdir()
        (root / "records").mkdir()
        cp = checkpoint or {
            "schema_version": 1,
            "status": "uninitialized",
            "highest_verified_index": None,
            "updated_utc": None,
            "source_commit": None,
            "record_count": 0,
            "note": "Waiting for reviewed data"
        }
        (root / "global" / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        for record in records or []:
            (root / "records" / (record["record_id"] + ".json")).write_text(
                json.dumps(record), encoding="utf-8"
            )
        return root

    def test_uninitialized_empty_network_is_valid(self) -> None:
        result = validate_network(self.make_root())
        self.assertEqual(result["status"], "uninitialized")
        self.assertIsNone(result["highest_verified_index"])

    def test_contiguous_verified_checkpoint_is_valid(self) -> None:
        record = base_record()
        checkpoint = {
            "schema_version": 1,
            "status": "initialized",
            "highest_verified_index": 2,
            "updated_utc": "2026-11-13T12:30:00Z",
            "source_commit": "abcdef0123456789",
            "record_count": 1,
            "note": "Reviewed checkpoint"
        }
        result = validate_network(self.make_root(checkpoint, [record]))
        self.assertEqual(result["highest_verified_index"], 2)

    def test_gap_is_rejected(self) -> None:
        record = base_record()
        record["entries"][1]["index"] = 3
        with self.assertRaises(ValidationError):
            validate_network(self.make_root(records=[record]))

    def test_unverified_entry_cannot_advance_checkpoint(self) -> None:
        record = base_record()
        record["entries"][1]["status"] = "evaluated"
        record["entries"][1]["verification"]["certified"] = False
        checkpoint = {
            "schema_version": 1,
            "status": "initialized",
            "highest_verified_index": 2,
            "updated_utc": "2026-11-13T12:30:00Z",
            "source_commit": "abcdef0123456789",
            "record_count": 1,
            "note": "Should fail"
        }
        with self.assertRaises(ValidationError):
            validate_network(self.make_root(checkpoint, [record]))

    def test_inverted_interval_is_rejected(self) -> None:
        record = base_record()
        record["entries"][0]["ordinate_interval"] = ["9.0", "1.0"]
        with self.assertRaises(ValidationError):
            validate_network(self.make_root(records=[record]))

    def test_checkpoint_cannot_skip_missing_indices(self) -> None:
        record = base_record()
        record["start_index"] = 2
        record["end_index"] = 3
        record["entries"][0]["index"] = 2
        record["entries"][1]["index"] = 3
        checkpoint = {
            "schema_version": 1,
            "status": "initialized",
            "highest_verified_index": 3,
            "updated_utc": "2026-11-13T12:30:00Z",
            "source_commit": "abcdef0123456789",
            "record_count": 1,
            "note": "Should fail"
        }
        with self.assertRaises(ValidationError):
            validate_network(self.make_root(checkpoint, [record]))


if __name__ == "__main__":
    unittest.main()
