"""Offline tests for the public network client."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from riemann_network.client import (
    NetworkClient,
    NetworkError,
    NetworkResponse,
    _parse_checkpoint,
    _validate_record_payload,
)


class ClientTests(unittest.TestCase):
    def test_uninitialized_checkpoint_is_not_zero(self) -> None:
        result = _parse_checkpoint({
            "schema_version": 1,
            "status": "uninitialized",
            "highest_verified_index": None,
            "updated_utc": None,
            "source_commit": None,
            "record_count": 0
        })
        self.assertIsNone(result.highest_verified_index)

    def test_invalid_initialized_checkpoint_rejected(self) -> None:
        with self.assertRaises(NetworkError):
            _parse_checkpoint({
                "schema_version": 1,
                "status": "initialized",
                "highest_verified_index": None,
                "updated_utc": "2026-11-13T12:00:00Z",
                "source_commit": "abcdef0123",
                "record_count": 1
            })

    def test_record_range_must_be_contiguous(self) -> None:
        payload = {
            "schema_version": 1,
            "record_id": "batch-1",
            "start_index": 1,
            "end_index": 2,
            "entries": [{"index": 1}, {"index": 3}]
        }
        with self.assertRaises(NetworkError):
            _validate_record_payload(payload, "batch-1.json")

    def test_filename_is_safely_restricted(self) -> None:
        client = NetworkClient()
        with self.assertRaises(ValueError):
            client.fetch_record("../checkpoint.json")

    def test_stale_cache_is_used_when_refresh_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = NetworkClient(cache_dir=directory)
            cached_data = {"sample": True}
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            client._write_cache("https://example.invalid/data", cached_data, now)
            with patch("riemann_network.client.urlopen", side_effect=OSError("offline")):
                response = client._get_json("https://example.invalid/data", force_refresh=True)
            self.assertEqual(response.data, cached_data)
            self.assertTrue(response.stale)
            self.assertEqual(response.source, "cache")


if __name__ == "__main__":
    unittest.main()
